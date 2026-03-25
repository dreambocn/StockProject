from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # 所有 ORM 模型统一继承此基类，确保元数据可用于自动建表与迁移补齐。
    pass
