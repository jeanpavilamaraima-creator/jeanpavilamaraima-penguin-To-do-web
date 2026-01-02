import os
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware 


app = FastAPI()
# La secret_key es necesaria para manejar las sesiones (cookies)
app.add_middleware(SessionMiddleware, secret_key="una_clave_muy_secreta_123")
templates = Jinja2Templates(directory="templates")

# Montar archivos estáticos para el Modo Oscuro (theme.js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuración de Seguridad para contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    descripcion_profunda = Column(String, default="")
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    propietario = relationship("Usuario", back_populates="tareas")

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_password_hash(password):
    return pwd_context.hash(password[:72])

def verify_password(plain_password, hashed_password):
    
    return pwd_context.verify(plain_password[:72], hashed_password)

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id: return None
    return db.query(Usuario).filter(Usuario.id == user_id).first()

def require_auth(user: Usuario = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuario o contraseña incorrectos"})
    
    # Guardar sesión
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/registro")
async def registro_page(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})

@app.post("/registro")
async def registro_action(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # Verificar si el usuario ya existe
    existe = db.query(Usuario).filter(Usuario.username == username).first()
    if existe:
        return templates.TemplateResponse("registro.html", {"request": request, "error": "El nombre de usuario ya está en uso"})
    
    hashed = pwd_context.hash(password)
    nuevo_usuario = Usuario(username=username, hashed_password=hashed)
    db.add(nuevo_usuario)
    db.commit()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)



@app.get("/")
async def inicio(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    mis_tareas = db.query(Tarea).filter(Tarea.usuario_id == user.id).all()
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    tareas_organizadas = {d: [t for t in mis_tareas if t.dia == d] for d in dias}
    return templates.TemplateResponse("agregar_tareas.html", {
        "request": request, 
        "tareas_por_dia": tareas_organizadas, 
        "user": user
    })

@app.post("/agregar")
async def agregar(descripcion: str = Form(...), fecha_limite: str = Form(...), dia: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    fecha_dt = datetime.strptime(fecha_limite, "%Y-%m-%dT%H:%M")
    nueva = Tarea(descripcion=descripcion, fecha_limite=fecha_dt, dia=dia, usuario_id=user.id)
    db.add(nueva)
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/tarea/{tarea_id}")
async def ver_editor_tarea(request: Request, tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if not tarea: return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("tarea.html", {"request": request, "tarea": tarea, "user": user})

@app.post("/editar/{tarea_id}")
async def editar_tarea(tarea_id: int, descripcion: str = Form(...), fecha_limite: str = Form(...), dia: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if tarea:
        tarea.descripcion = descripcion
        tarea.fecha_limite = datetime.strptime(fecha_limite, "%Y-%m-%dT%H:%M")
        tarea.dia = dia
        db.commit()
    return RedirectResponse(url=f"/tarea/{tarea_id}", status_code=303)

@app.post("/guardar_detalle/{tarea_id}")
async def guardar_detalle(tarea_id: int, detalle_profundo: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if tarea:
        tarea.descripcion_profunda = detalle_profundo
        db.commit()
    return RedirectResponse(url=f"/tarea/{tarea_id}", status_code=303)

@app.post("/finalizar/{tarea_id}")
async def finalizar(tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.usuario_id == user.id).first()
    if tarea:
        db.delete(tarea)
        db.commit()
    return RedirectResponse("/", status_code=303)