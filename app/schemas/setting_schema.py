from pydantic import BaseModel
from typing import Optional


# SECURITY
class SecuritySettingUpdate(BaseModel):
    session_timeout: Optional[int]

class SecuritySettingResponse(BaseModel):

    session_timeout: Optional[int]

    class config:
        from_attributes = True




    
    
