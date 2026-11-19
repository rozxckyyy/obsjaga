from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import database_url
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
