from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class LoreEntityNode(BaseModel):
    """
    Schema for a single entity in the static entity dictionary.
    """
    canonical_name: str = Field(description="The canonical name of the entity, e.g., 'Startorch Academy'")
    aliases: List[str] = Field(default_factory=list, description="Alternative names for this entity")
    type: str = Field(description="Type of entity: Organization, Character, Region, Faction, etc.")
    description: Optional[str] = Field(default=None, description="Short summary of the entity")
    parent: Optional[str] = Field(default=None, description="Canonical name of the parent entity")
    children: List[str] = Field(default_factory=list, description="Canonical names of child entities")
    region: Optional[str] = Field(default=None, description="Region canonical name")
    faction: Optional[str] = Field(default=None, description="Faction canonical name")
    related: List[str] = Field(default_factory=list, description="Canonical names of related entities")

class EntityDictionary(BaseModel):
    """
    The full entity dictionary loaded into memory.
    """
    entities: Dict[str, LoreEntityNode] = Field(default_factory=dict)
