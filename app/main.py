import bcrypt
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from sqlalchemy import text


from database.connection import engine
from database.models import Base
from database.models import Message, MessageRecipient, User
from database.deps import get_db


from routes.auth import verify_password, get_password_hash, create_access_token, verify_token


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

@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    print(f"\n=== LOGIN ATTEMPT ===")
    print(f"Email: {email}")
    print(f"Password entered: '{password}'")
    print(f"Password length: {len(password)} chars, {len(password.encode('utf-8'))} bytes")
    
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        print(f"User not found!")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    print(f"User found: {user.username}")
    print(f"Stored hash: {user.password_hash}")
    print(f"Hash type: {type(user.password_hash)}")
    
    # Manual verification test
    try:
        password_bytes = password.encode('utf-8')
        hash_bytes = user.password_hash.encode('utf-8')
        
        print(f"Password bytes: {password_bytes}")
        print(f"Hash bytes length: {len(hash_bytes)}")
        
        result = bcrypt.checkpw(password_bytes, hash_bytes)
        print(f"bcrypt.checkpw result: {result}")
        
        if not result:
            print(f"Password verification FAILED")
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
    except Exception as e:
        print(f"Exception during verification: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    print(f"Login successful!")
    
    token = create_access_token(data={"sub": user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True)
    return response

@app.get("/register", response_class=HTMLResponse)
def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_user(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    print(f"DEBUG - Registering user:")
    print(f"  Email: {email}")
    print(f"  Username: {username}")
    print(f"  Password length: {len(password)} chars, {len(password.encode('utf-8'))} bytes")
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username already exists
    existing_username = db.query(User).filter(User.username == username).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Hash the password (NOT the SECRET_KEY!)
    hashed_password = get_password_hash(password)
    print(f"  Hashed password successfully")
    
      # Create new user
    new_user = User(
        email=email,
        username=username,
        password_hash=hashed_password
    )
    db.add(new_user)
    db.commit()

    print(f"  User created successfully with ID: {new_user.id}")
    return RedirectResponse(url="/?registered=true", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), current_user: User= Depends(verify_token)):
    Sender = aliased(User)
    
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
        "messages": messages,
        "current_user": current_user
    })
    
@app.get("/users", response_class=HTMLResponse)
def users(request: Request, db: Session = Depends(get_db), current_user: User = Depends(verify_token)):
    users_list = db.query(User).all()

    return templates.TemplateResponse("user.html", {
        "request": request,
        "users": users_list,
        "current_user": current_user
    })

@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request, db: Session = Depends(get_db), current_user: User = Depends(verify_token)):
    Sender = aliased(User)
    
    messages_query = db.query(
        Message.id,
        Message.body,
        Message.created_at,
        Sender.username.label('sender_username')
    ).join(Sender, Message.sender_id == Sender.id).all()
    
    messages = []
    for msg in messages_query:
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
    
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "messages": messages,
        "current_user": current_user
    })


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

@app.get("/debug/users")
def debug_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at
    } for user in users]
