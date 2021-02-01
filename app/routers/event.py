from datetime import datetime
from operator import attrgetter
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from starlette import status
from starlette.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND


from app.database.database import get_db
from app.database.models import Event, User, UserEvent
from app.dependencies import logger, templates
from app.internal.event import validate_zoom_link
from app.internal.utils import create_model
from app.routers.user import create_user


router = APIRouter(
    prefix="/event",
    tags=["event"],
    responses={404: {"description": "Not found"}},
)


@router.get("/edit")
async def eventedit(request: Request):
    return templates.TemplateResponse("event/eventedit.html",
                                      {"request": request})


@router.post("/edit")
async def create_new_event(request: Request, session=Depends(get_db)):
    data = await request.form()
    title = data['title']
    content = data['description']
    start = datetime.strptime(data['start_date'] + ' ' + data['start_time'],
                              '%Y-%m-%d %H:%M')
    end = datetime.strptime(data['end_date'] + ' ' + data['end_time'],
                            '%Y-%m-%d %H:%M')
    user = session.query(User).filter_by(id=1).first()
    user = user if user else create_user("u", "p", "e@mail.com", session)
    owner_id = user.id
    location_type = data['location_type']
    is_zoom = location_type == 'vc_url'
    location = data['location']

    if is_zoom:
        validate_zoom_link(location)

    event = create_event(session, title, start, end, owner_id, content,
                         location)
    return RedirectResponse(router.url_path_for('eventview',
                                                event_id=event.id),
                            status_code=HTTP_302_FOUND)


@router.get("/{event_id}")
async def eventview(request: Request, event_id: int,
                    db: Session = Depends(get_db)):
    try:
        event = get_event_by_id(db, event_id)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Event not found")
    except MultipleResultsFound:
        raise HTTPException(status_code=500, detail="Multiple events found")
    start_format = '%A, %d/%m/%Y %H:%M'
    end_format = ('%H:%M' if event.start.date() == event.end.date()
                  else start_format)
    return templates.TemplateResponse("event/eventview.html",
                                      {"request": request, "event": event,
                                       "start_format": start_format,
                                       "end_format": end_format})


@router.delete("/{event_id}")
def delete_event(request: Request, event_id: int,
                 db: Session = Depends(get_db)):
    # TODO: Check if the user is the owner of the event.
    try:
        event = get_event_by_id(db, event_id)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Event not found")
    except MultipleResultsFound:
        raise HTTPException(status_code=500, detail="Multiple events found")

    participants = get_participants_emails_by_event(db, event_id)

    try:
        db.delete(event)
        db.query(UserEvent).filter_by(event_id=event_id).delete()
        db.commit()
    except (SQLAlchemyError, TypeError):
        return templates.TemplateResponse(
            "event/eventview.html", {"request": request, "event_id": event_id},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if participants and event.start > datetime.now():
        pass
        # TODO: Send them a cancellation notice
        # if the deletion is successful
    return RedirectResponse(
        url="/calendar", status_code=status.HTTP_200_OK)


def get_event_by_id(db: Session, event_id: int) -> Event:
    """Gets a single event by id"""
    if not isinstance(db, Session):
        raise AttributeError(
            f'Could not connect to database. '
            f'db instance type received: {type(db)}')
    try:
        event = db.query(Event).filter_by(id=event_id).one()
    except NoResultFound:
        raise NoResultFound(f"Event ID does not exist. ID: {event_id}")
    except MultipleResultsFound:
        error_message = (
            f'Multiple results found when getting event. Expected only one. '
            f'ID: {event_id}')
        logger.critical(error_message)
        raise MultipleResultsFound(error_message)
    return event


def is_date_before(start_date: datetime, end_date: datetime) -> bool:
    """Check if the start date is earlier than the end date"""

    return start_date < end_date


def is_it_possible_to_change_dates(old_event: Event,
                                   event: Dict[str, Any]) -> bool:
    return is_date_before(
        event.get('start', old_event.start),
        event.get('end', old_event.end))


def get_items_that_can_be_updated(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only that keys to update"""

    return {i: event[i] for i in (
        'title', 'start', 'end', 'content', 'location') if i in event}


def update_event(event_id: int, event: Dict, db: Session
                 ) -> Optional[Event]:
    # TODO Check if the user is the owner of the event.

    event_to_update = get_items_that_can_be_updated(event)
    if not event_to_update:
        return None
    try:
        old_event = get_event_by_id(db, event_id)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Event not found")
    except MultipleResultsFound:
        raise HTTPException(status_code=500, detail="Multiple events found")
    try:
        if not is_it_possible_to_change_dates(old_event, event_to_update):
            return None

        # Update database
        db.query(Event).filter(Event.id == event_id).update(
            event_to_update, synchronize_session=False)
        db.commit()

        # TODO: Send emails to recipients.
    except (AttributeError, SQLAlchemyError, TypeError):
        return None

    return get_event_by_id(db=db, event_id=event_id)


def create_event(db, title, start, end, owner_id, content=None, location=None):
    """Creates an event and an association."""

    event = create_model(
        db, Event,
        title=title,
        start=start,
        end=end,
        content=content,
        owner_id=owner_id,
        location=location,
    )
    create_model(
        db, UserEvent,
        user_id=owner_id,
        event_id=event.id
    )
    return event


def sort_by_date(events: List[Event]) -> List[Event]:
    """Sorts the events by the start of the event."""

    temp = events.copy()
    return sorted(temp, key=attrgetter('start'))


def get_participants_emails_by_event(db: Session, event_id: int) -> List[str]:
    """Returns a list of all the email address of the event invited users,
        by event id."""

    return (
        [email[0] for email in db.query(User.email).
            select_from(Event).
            join(UserEvent, UserEvent.event_id == Event.id).
            join(User, User.id == UserEvent.user_id).
            filter(Event.id == event_id).
            all()]


@router.delete("/{event_id}")
def delete_event(request: Request,
                 event_id: int,
                 db: Session = Depends(get_db)):

    # TODO: Check if the user is the owner of the event.
    event = by_id(db, event_id)
    participants = get_participants_emails_by_event(db, event_id)
    try:
        # Delete event
        db.delete(event)

        # Delete user_event
        db.query(UserEvent).filter(UserEvent.event_id == event_id).delete()

        db.commit()

    except (SQLAlchemyError, TypeError):
        return templates.TemplateResponse(
            "event/eventview.html", {"request": request, "event_id": event_id},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if participants and event.start > datetime.now():
        pass
        # TODO: Send them a cancellation notice
        # if the deletion is successful
    return RedirectResponse(
        url="/calendar", status_code=status.HTTP_200_OK)


def check_date_validation(start_time, end_time) -> bool:
    """Check if the start_date is smaller then the end_time"""

    try:
        return start_time < end_time
    except TypeError:
        return False


def add_new_event(values: dict, db) -> Optional[Event]:
    """Get User values and the DB Session insert the values
    to the DB and refresh it exception in case that the keys
    in the dict is not match to the fields in the DB
    return the Event Class item"""

    if not check_date_validation(values['start'], values['end']):
        return None
    else:
        try:
            new_event = create_model(
                        db, Event, **values)
            create_model(
                    db, UserEvent,
                    user_id=values['owner_id'],
                    event_id=new_event.id
                )
            return new_event
        except (AssertionError, AttributeError, TypeError) as e:
            logger.exception(e)
            return None
