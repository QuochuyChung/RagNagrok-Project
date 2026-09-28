from sqlalchemy.orm import DeclarativeBase

"""
    Cứ class nào kế thừa base thì sẽ được DeclarativeBase đăng kí vào bên trong metadata của Base.metadata
"""
class Base(DeclarativeBase):
    pass