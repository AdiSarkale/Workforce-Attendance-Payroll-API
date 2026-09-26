from pydantic import BaseModel

class Site(BaseModel):
    id: int
    organization_id: int
    name: str
    active: bool = True
