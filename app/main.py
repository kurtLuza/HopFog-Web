from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from sqlalchemy import text


from database.connection import engine
from database.models import Base
from database.models import Message, MessageRecipient, User
from database.deps import get_db


from routes.users import router as users_router
from routes.messages import router as messages_router


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(users_router)
app.include_router(messages_router)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    Sender = aliased(User)
    Recipient = aliased(User)
    
    # Query messages with sender and recipients
    messages_query = db.query(
        Message.id,
        Message.body,
        Message.created_at,
        Sender.username.label('sender_username')
    ).join(Sender, Message.sender_id == Sender.id).all()
    
    # Format messages for template
    messages = []
    for msg in messages_query:
        # Get recipients for this message
        recipients = db.query(User.username).join(
            MessageRecipient, User.id == MessageRecipient.user_id
        ).filter(MessageRecipient.message_id == msg.id).all()
        
        messages.append({
            'id': msg.id,
            'from': msg.sender_username,
            'to': [r.username for r in recipients],
            'message': msg.body,
            'date': msg.created_at
        })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "messages": messages
    })
    
@app.get("/users", response_class=HTMLResponse)
def users(request: Request):
    return templates.TemplateResponse("user.html", {"request": request})

@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})

@app.get("/test-db")
def test_db():
    return {"ok": True, "db_file": "capstone.db (SQLite)"}

@app.get("/db-ping")
def db_ping(db: Session = Depends(get_db)):
    return {"db_ok": db.execute(text("SELECT 1")).scalar()}

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    db.query(MessageRecipient).filter(MessageRecipient.message_id == message_id).delete()
    
    # Delete the message
    message = db.query(Message).filter(Message.id == message_id).first()
    if message:
        db.delete(message)
        db.commit()
        return {"message": "Message deleted successfully"}
    return {"error": "Message not found"}