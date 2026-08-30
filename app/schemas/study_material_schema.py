# schemas/study_material.py
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional


class StudyMaterialBase(BaseModel):
    """Base schema with common fields"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    tenant_id: str = Field(...)
    subject_name: str = Field(..., min_length=1, max_length=50)
    downloadable: bool = Field(default=False)


class StudyMaterialCreate(StudyMaterialBase):
    class_code: str = Field(..., min_length=1, max_length=20)


    


class StudyMaterialUpdate(BaseModel):
    """Schema for updating study material metadata"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)


class StudyMaterialResponse(StudyMaterialBase):
    """Schema for returning study material data"""
    id: int
    file_url: str
    file_type: str
    uploaded_at: datetime
    uploaded_by: Optional[int]
    
    class Config:
        from_attributes = True  
        


class StudyMaterialListResponse(BaseModel):
    """Schema for list response"""
    count: int
    data: list[StudyMaterialResponse]


class FileUploadResponse(BaseModel):
    """Schema for successful file upload"""
    message: str
    data: StudyMaterialResponse


class DeleteResponse(BaseModel):
    """Schema for deletion response"""
    message: str
    id: int
    title: str


class UpdateResponse(BaseModel):
    """Schema for update response"""
    message: str
    data: dict