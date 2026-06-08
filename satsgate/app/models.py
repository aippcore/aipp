from sqlalchemy import Column, Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Client(Base):
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True, index=True)
    api_key_hash = Column(String, unique=True, nullable=False)
    credits = Column(Integer, nullable=False, default=0)
    payee_lightning_address = Column(String, nullable=True)
    created_at = Column(Integer, nullable=False)

    ledgers = relationship("Ledger", back_populates="client")
    topups = relationship("Topup", back_populates="client")
    verifications = relationship("Verification", back_populates="client")


class Ledger(Base):
    __tablename__ = 'ledger'
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    delta_credits = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    ref = Column(String, nullable=True)
    created_at = Column(Integer, nullable=False)

    client = relationship("Client", back_populates="ledgers")


class Topup(Base):
    __tablename__ = 'topups'
    
    id = Column(Integer, primary_key=True, index=True)
    payment_hash = Column(String, unique=True, nullable=False)
    invoice = Column(String, nullable=False)
    sats = Column(Integer, nullable=False)
    credits = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=True)
    created_at = Column(Integer, nullable=False)
    settled_at = Column(Integer, nullable=True)

    client = relationship("Client", back_populates="topups")


class Verification(Base):
    __tablename__ = 'verifications'
    __table_args__ = (
        UniqueConstraint('client_id', 'payment_hash', name='uix_client_payment_hash'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    payment_hash = Column(String, nullable=False)
    resource = Column(String, nullable=True)
    created_at = Column(Integer, nullable=False)

    client = relationship("Client", back_populates="verifications")

Index('idx_ledger_client_id', Ledger.client_id, Ledger.id)
Index('idx_ledger_client_created', Ledger.client_id, Ledger.created_at)
Index('idx_topups_client_created', Topup.client_id, Topup.created_at)
Index('idx_verifications_client_created', Verification.client_id, Verification.created_at)
