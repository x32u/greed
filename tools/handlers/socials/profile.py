from pydantic import BaseModel
from typing import Optional


class ServerProfile(BaseModel):
    """
    Model for discord server profiles
    """

    banner: Optional[str]
    bio: Optional[str]
