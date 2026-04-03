from database import db
from datetime import datetime


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    venue = db.Column(db.String(200))
    location = db.Column(db.String(300))
    date = db.Column(db.String(100))
    start_time = db.Column(db.String(50))
    entry_price = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    description = db.Column(db.Text)
    genre = db.Column(db.String(100))
    dress_code = db.Column(db.String(100))
    age_limit = db.Column(db.String(50))
    instagram_profile = db.Column(db.String(100))
    instagram_post_url = db.Column(db.String(500))
    image_url = db.Column(db.String(500))
    raw_caption = db.Column(db.Text)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'venue': self.venue,
            'location': self.location,
            'date': self.date,
            'start_time': self.start_time,
            'entry_price': self.entry_price,
            'phone': self.phone,
            'description': self.description,
            'genre': self.genre,
            'dress_code': self.dress_code,
            'age_limit': self.age_limit,
            'instagram_profile': self.instagram_profile,
            'instagram_post_url': self.instagram_post_url,
            'image_url': self.image_url,
        }


class ScrapedProfile(db.Model):
    __tablename__ = 'scraped_profiles'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    last_scraped = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'is_active': self.is_active,
            'last_scraped': self.last_scraped.isoformat() if self.last_scraped else None,
        }