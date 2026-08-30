
from pydantic import BaseModel, EmailStr, Field,computed_field
from typing import Optional,List,Dict,Any
from ..models.user_model import UserRoleEnum
from datetime import date, datetime
from .permission_schema import PermissionDetail
class UserCreate(BaseModel):
    """
    only necessary field
    """
    
    # User Fields
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: UserRoleEnum= Field(..., description="User role")


    # User Contact Info
    contact_num: str = Field(..., min_length=10, max_length=15)
    contact_num_country_code: str = Field("91", min_length=1, max_length=5)


    # User Personal Info
    address: Optional[str] = Field(None, max_length=500)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: str = Field("India", min_length=2, max_length=50)


    

class UsersBasicResponse(BaseModel):
    
    # User Fields
    id: int
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    user_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: UserRoleEnum= Field(..., description="User role")
    contact_num: str = Field(..., min_length=10, max_length=15)
    contact_num_country_code: str = Field("91", min_length=1, max_length=5)
    is_block: bool = Field(default=False)
    deleted_date: Optional[date] = Field(None)
    profile_image_raw: str | None = Field(
        alias="profile_image",
        exclude=True
    )
    model_config = {"from_attributes": True}
    @computed_field
    @property
    def profile_image(self) -> dict | None:
        if not self.profile_image_raw:
            return None

        return {
            "thumb": f"/api/institutions/users/{self.id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{self.id}/profile-image?type=main"
        }



        
class UsersResponse(BaseModel):
    id: int
    user_name: str = Field(..., min_length=2, max_length=50)
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: UserRoleEnum = Field(..., description="User role")
    joined_date: date
    permissions: List[PermissionDetail]
    is_block: bool = Field(default=False)

    # Contact Information
    contact_num: str = Field(..., min_length=10, max_length=15)
    contact_num_country_code: str = Field("91", min_length=1, max_length=5)
    alternative_contact_num: Optional[str] = Field(None, max_length=15)
    alternative_contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)

    # Profile & Address
    address: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: str = Field("India", min_length=2, max_length=50)

    # Personal Information
    gender: Optional[str] = Field(None, max_length=10)
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = Field(None, max_length=5)

    # Gamification
    total_score: Optional[int] = Field(0, ge=0)
    score_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    # Example: [{"score_get": 20, "reason": "weekly test", "date": "2 aug", "by": "ramesh sir"}]
    deleted_date: Optional[date] = Field(None)
    # Timestamps
    created_at: datetime
    updated_at: datetime

    profile_image_raw: str | None = Field(
        alias="profile_image",
        exclude=True
    )
    model_config = {"from_attributes": True}
    @computed_field
    @property
    def profile_image(self) -> dict | None:
        if not self.profile_image_raw:
            return None

        return {
            "thumb": f"/api/institutions/users/{self.id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{self.id}/profile-image?type=main"
        }




 
class UserUpdate(BaseModel):
    user_name: Optional[str] = Field(None, min_length=2, max_length=50)
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None


    # Contact Information
    contact_num: Optional[str] = Field(None, min_length=10, max_length=15)
    contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)
    alternative_contact_num: Optional[str] = Field(None, max_length=15)
    alternative_contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)

    # Profile & Address
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, min_length=2, max_length=50)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: Optional[str] = Field("India", min_length=2, max_length=50)

    # Personal Information
    gender: Optional[str] = Field(None, max_length=10)
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = Field(None, max_length=5)


# for auth
class CurrentUserResponse(BaseModel):
    id: int
    user_name: str
    email: EmailStr

    role: UserRoleEnum
    permissions: List[str]
    first_name: str
    last_name: str 
    tenant_id: str
    is_block: bool
    deleted_date: Optional[date]
    is_profile_complete : bool

    profile_image_raw: str | None = Field(
        alias="profile_image",
        exclude=True
    )
    model_config = {"from_attributes": True}
    @computed_field
    @property
    def profile_image(self) -> dict | None:
        if not self.profile_image_raw:
            return None

        return {
            "thumb": f"/api/institutions/users/{self.id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{self.id}/profile-image?type=main"
        }



 
