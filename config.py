import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'OracoloLens2025xK9mP3qR7')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///oracolo_lens.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    APP_NAME = 'Oracolo Lens'
    APP_VERSION = '1.0.0'
