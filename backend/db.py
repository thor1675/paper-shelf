import os

from sqlmodel import Session, create_engine

# pool_pre_ping: 使う前に接続が生きているか確かめる（Supabase などは使っていない接続を切ることがある）
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

def get_session():
    with Session(engine) as session:
        yield session
