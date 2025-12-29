import os
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import bcrypt
from starlette.middleware.sessions import SessionMiddleware 

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="tu_clave_secreta") # Necesario para login


SQLALCHEMY_DATABASE_URL = "sqlite:///./tareas.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    hashed_password = Column(String)
    tareas = relationship("Tarea", back_populates="propietario")

class Tarea(Base):
    __tablename__ = "tareas"
    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String)
    fecha_limite = Column(DateTime)
    dia = Column(String)
    notificada = Column(Boolean, default=False) # Para no repetir la notificación
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
    if not username: raise HTTPException(status_code=303, headers={"Location": "/login"})
    return db.query(Usuario).filter(Usuario.username == username).first()

@app.get("/api/check-notificaciones")
async def check_notificaciones(db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    ahora = datetime.now()
    # Buscamos tareas que ya pasaron su hora y no han sido notificadas
    pendientes = db.query(Tarea).filter(
        Tarea.usuario_id == user.id,
        Tarea.fecha_limite <= ahora,
        Tarea.notificada == False
    ).all()
    
    data = [{"id": t.id, "descripcion": t.descripcion} for t in pendientes]
    return JSONResponse(content=data)

@app.post("/api/marcar-notificada/{tarea_id}")
async def marcar_notificada(tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if tarea:
        tarea.notificada = True
        db.commit()
    return {"status": "ok"}

@app.get("/")
async def inicio(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    mis_tareas = db.query(Tarea).filter(Tarea.usuario_id == user.id).all()
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    tareas_organizadas = {d: [t for t in mis_tareas if t.dia == d] for d in dias}
    return templates.TemplateResponse("agregar_tareas.html", {"request": request, "tareas_por_dia": tareas_organizadas, "user": user})

@app.post("/agregar")
async def agregar(descripcion: str = Form(...), fecha_limite: str = Form(...), dia: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    fecha_dt = datetime.strptime(fecha_limite, "%Y-%m-%dT%H:%M")
    nueva = Tarea(descripcion=descripcion, fecha_limite=fecha_dt, dia=dia, usuario_id=user.id)
    db.add(nueva)
    db.commit()
    return RedirectResponse("/", status_code=300)

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


@app.post("/finalizar/{tarea_id}")
async def finalizar(tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    t = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if t:
        db.delete(t)
        db.commit()
    return RedirectResponse("/", status_code=303)
