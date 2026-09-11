from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str
    SUPABASE_SERVICE_ROLE_KEY: str
    INVITE_REDIRECT_URL: str = "https://your-frontend.com/set-password"


    class Config:
        env_file = ".env"

settings = Settings()