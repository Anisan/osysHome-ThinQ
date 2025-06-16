from app.database import Column, Model, SurrogatePK, db

class ThinqDevices(SurrogatePK, Model):
    __tablename__ = 'thinq_devices'
    alias = Column(db.String(100))
    uuid = Column(db.String(100))
    device_type = Column(db.String(100))
    model_name = Column(db.String(100))
    model_protocol = Column(db.String(100))
    online = Column(db.Boolean, default=False)
    updated = Column(db.DateTime)
