import os
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from fastapi import FastAPI, Request, Form, Depends, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import bcrypt

# --- CONFIGURACIÓN DE GOOGLE OAUTH Y SESIÓN ---
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Clave secreta para manejar las sesiones (Obligatoria para Google Auth)
app.add_middleware(SessionMiddleware, secret_key="clave_secreta_para_produccion_123")

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # Solo para desarrollo lo

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "tu_correo@gmail.com" 
SENDER_PASSWORD = "xxxx xxxx xxxx xxxx" 


oauth = OAuth()
oauth.register(
    name='google',
    client_id='TU_CLIENT_ID.apps.googleusercontent.com',
    client_secret='TU_CLIENT_SECRET',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


SQLALCHEMY_DATABASE_URL = "sqlite:///./tareas.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    email = Column(String, nullable=True) # Correo vinculado de Google
    tareas = relationship("Tarea", back_populates="propietario")

class Tarea(Base):
    __tablename__ = "tareas"
    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String, index=True)
    fecha_limite = Column(DateTime)
    descripcion_profunda = Column(String, default="")
    dia = Column(String, default="Lunes")
    email_enviado = Column(Boolean, default=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    propietario = relationship("Usuario", back_populates="tareas")

Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

async def require_auth(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("user")
    if not username:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user

def enviar_notificacion(destinatario, tarea_nombre):
    try:
        msg = MIMEText(f"La tarea '{tarea_nombre}' ha vencido.")
        msg['Subject'] = f"🔔 Alerta: {tarea_nombre}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = destinatario
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls()
            s.login(SENDER_EMAIL, SENDER_PASSWORD)
            s.send_message(msg)
        return True
    except: return False



@app.get("/")
async def inicio(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    mis_tareas = db.query(Tarea).filter(Tarea.usuario_id == user.id).all()
    ahora = datetime.now()

    if user.email:
        for t in mis_tareas:
            if not t.email_enviado and t.fecha_limite <= ahora:
                if enviar_notificacion(user.email, t.descripcion):
                    t.email_enviado = True
                    db.commit()

    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    tareas_organizadas = {d: [t for t in mis_tareas if t.dia == d] for d in dias}
    return templates.TemplateResponse("agregar_tareas.html", {"request": request, "tareas_por_dia": tareas_organizadas, "user": user})

@app.get("/link-google")
async def link_google(request: Request):
    return await oauth.google.authorize_redirect(request, request.url_for('auth_google'))

@app.get("/auth-google")
async def auth_google(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    username = request.session.get("user")
    if username and user_info:
        u = db.query(Usuario).filter(Usuario.username == username).first()
        u.email = user_info['email']
        db.commit()
    return RedirectResponse("/")

@app.get("/unlink-google")
async def unlink_google(db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    user.email = None
    db.commit()
    return RedirectResponse("/")

@app.post("/registro")
async def registrar(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(Usuario).filter(Usuario.username == username).first():
        return templates.TemplateResponse("registro.html", {"request": request, "error": "Usuario ya existe"})
    
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    nuevo = Usuario(username=username, hashed_password=hashed)
    db.add(nuevo)
    db.commit()
    return RedirectResponse("/login", status_code=303)

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(Usuario).filter(Usuario.username == username).first()
    if not u or not bcrypt.checkpw(password.encode('utf-8'), u.hashed_password.encode('utf-8')):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales incorrectas"})
    request.session["user"] = username
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.post("/agregar")
async def agregar(descripcion: str = Form(...), fecha_limite: str = Form(...), dia: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    fecha_dt = datetime.strptime(fecha_limite, "%Y-%m-%dT%H:%M")
    nueva = Tarea(descripcion=descripcion, fecha_limite=fecha_dt, dia=dia, usuario_id=user.id)
    db.add(nueva)
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/finalizar/{tarea_id}")
async def finalizar(tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    t = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if t:
        db.delete(t)
        db.commit()
    return RedirectResponse("/", status_code=303)