from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'cf',
     'default_range': 'string',
     'description': 'LinkML schema for the business-document domain entities '
                    'produced by the 6 SDLC role agents (product-manager, '
                    'architect, ui-designer, tech-lead, qa-engineer, devops). '
                    'Models intra-layer composition and the cross-SDLC '
                    'traceability matrix that is the central value of the 0.5.0 KG '
                    'migration. Single source of truth — generates Pydantic v2 '
                    'models + OWL/SHACL.',
     'id': 'https://cataforge.dev/ontology/core',
     'imports': ['linkml:types'],
     'license': 'Apache-2.0',
     'name': 'cataforge-core',
     'prefixes': {'cf': {'prefix_prefix': 'cf',
                         'prefix_reference': 'https://cataforge.dev/ontology/'},
                  'cfgov': {'prefix_prefix': 'cfgov',
                            'prefix_reference': 'https://cataforge.dev/governance/'},
                  'cfprj': {'prefix_prefix': 'cfprj',
                            'prefix_reference': 'https://cataforge.dev/instance/'},
                  'dcterms': {'prefix_prefix': 'dcterms',
                              'prefix_reference': 'http://purl.org/dc/terms/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'owl': {'prefix_prefix': 'owl',
                          'prefix_reference': 'http://www.w3.org/2002/07/owl#'},
                  'prov': {'prefix_prefix': 'prov',
                           'prefix_reference': 'http://www.w3.org/ns/prov#'},
                  'rdf': {'prefix_prefix': 'rdf',
                          'prefix_reference': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'},
                  'rdfs': {'prefix_prefix': 'rdfs',
                           'prefix_reference': 'http://www.w3.org/2000/01/rdf-schema#'},
                  'sh': {'prefix_prefix': 'sh',
                         'prefix_reference': 'http://www.w3.org/ns/shacl#'},
                  'xsd': {'prefix_prefix': 'xsd',
                          'prefix_reference': 'http://www.w3.org/2001/XMLSchema#'}},
     'source_file': 'src/cataforge/domain/kg/schemas/core.yaml',
     'title': 'CataForge Core Business-Document Ontology',
     'types': {'ContentHash': {'base': 'str',
                               'description': 'SHA-256 hex of the source Markdown '
                                              'section, for stale-link detection.',
                               'from_schema': 'https://cataforge.dev/ontology/core',
                               'name': 'ContentHash',
                               'uri': 'xsd:string'},
               'EntityID': {'base': 'str',
                            'description': 'Frontmatter-level identifier, e.g. '
                                           'F-001, M-014, T-007. Pattern enforced '
                                           'per concrete class.',
                            'from_schema': 'https://cataforge.dev/ontology/core',
                            'name': 'EntityID',
                            'uri': 'xsd:string'},
               'SortKey': {'base': 'str',
                           'description': 'Deterministic natural-sort key used by '
                                          'KG → Markdown idempotent export. '
                                          'Format: '
                                          '`<class_code>:<zero-padded-numeric>` '
                                          'e.g. `F:000001`. Required on every '
                                          'concrete subclass of SoftwareArtifact.',
                           'from_schema': 'https://cataforge.dev/ontology/core',
                           'name': 'SortKey',
                           'uri': 'xsd:string'}}} )

class ProcessModelEnum(str, Enum):
    """
    SDLC process model selected at project scope.
    """
    waterfall = "waterfall"
    """
    Phase-gated sequential.
    """
    agile = "agile"
    """
    Sprint/Iteration based.
    """
    hybrid = "hybrid"
    """
    Mixed waterfall phases with internal sprints.
    """


class ArtifactStatusEnum(str, Enum):
    """
    Lifecycle state of any SoftwareArtifact.
    """
    draft = "draft"
    proposed = "proposed"
    approved = "approved"
    implemented = "implemented"
    verified = "verified"
    released = "released"
    deprecated = "deprecated"
    superseded = "superseded"


class PriorityEnum(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class RiskLevelEnum(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class TaskStatusEnum(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    review = "review"
    done = "done"
    cancelled = "cancelled"


class TestResultEnum(str, Enum):
    pass_ = "pass"
    fail = "fail"
    blocked = "blocked"
    skipped = "skipped"
    pending = "pending"


class EnvironmentEnum(str, Enum):
    dev = "dev"
    staging = "staging"
    production = "production"
    preview = "preview"


class ChangeStatusEnum(str, Enum):
    open = "open"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"



class SoftwareArtifact(ConfiguredBaseModel):
    """
    Common ancestor of every business-domain entity. All concrete subclasses carry a deterministic sort_key, a content_hash, and source_doc/section back-pointers for KG ⇄ Markdown idempotent round-trip.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'class_uri': 'cf:SoftwareArtifact',
         'from_schema': 'https://cataforge.dev/ontology/core'})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })


class Project(ConfiguredBaseModel):
    """
    Root container for a single user-software project.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Project',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'id': {'name': 'id', 'required': True},
                        'title': {'name': 'title', 'required': True}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    process_model: ProcessModelEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Project']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })


class WorkUnit(SoftwareArtifact):
    """
    Abstract unit of time/scope to which work is assigned.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'class_uri': 'cf:WorkUnit',
         'from_schema': 'https://cataforge.dev/ontology/core'})

    start_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    end_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })


class Phase(WorkUnit):
    """
    Waterfall phase. Honors the existing P-NNN frontmatter prefix.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Phase',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id', 'pattern': '^P-[0-9]{3,}$'}}})

    start_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    end_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^P-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Sprint(WorkUnit):
    """
    Agile sprint (fixed timebox).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Sprint',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id', 'pattern': '^S-[0-9]{3,}$'}}})

    start_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    end_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^S-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Iteration(WorkUnit):
    """
    Lightweight agile iteration (variable timebox).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Iteration',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id', 'pattern': '^I-[0-9]{3,}$'}}})

    start_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    end_date: Optional[date] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WorkUnit']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^I-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Milestone(SoftwareArtifact):
    """
    A point-in-time marker, not a timebox.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Milestone',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^MS-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^MS-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Requirement(SoftwareArtifact):
    """
    Common ancestor of all requirement-layer artifacts.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'class_uri': 'cf:Requirement',
         'from_schema': 'https://cataforge.dev/ontology/core'})

    refines: Optional[str] = Field(default=None, description="""This artifact elaborates a more abstract upstream artifact.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refined_by'} })
    refined_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refines'} })
    implemented_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'implements'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })


class Feature(Requirement):
    """
    Concrete product capability. Source: prd §2 F-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Feature',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^F-[0-9]{3,}$',
                                      'required': True}}})

    assigned_to_sprint: Optional[str] = Field(default=None, description="""Agile placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_phase: Optional[str] = Field(default=None, description="""Waterfall placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_work_unit: Optional[str] = Field(default=None, description="""Unified accessor (Phase or Sprint or Iteration).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    refines: Optional[str] = Field(default=None, description="""This artifact elaborates a more abstract upstream artifact.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refined_by'} })
    refined_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refines'} })
    implemented_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'implements'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^F-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class UserStory(Requirement):
    """
    Agile narrative. May refine a Feature.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:UserStory',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^US-[0-9]{3,}$'}}})

    refines: Optional[str] = Field(default=None, description="""This artifact elaborates a more abstract upstream artifact.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refined_by'} })
    refined_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refines'} })
    implemented_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'implements'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^US-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Epic(Requirement):
    """
    Large requirement aggregating multiple Features. Maps E-NNN (see §3.9 decision).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Epic',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^EP-[0-9]{3,}$'}}})

    refines: Optional[str] = Field(default=None, description="""This artifact elaborates a more abstract upstream artifact.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refined_by'} })
    refined_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'refines'} })
    implemented_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Requirement'], 'inverse': 'implements'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^EP-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class AcceptanceCriteria(SoftwareArtifact):
    """
    Verifiable condition attached to a Requirement or Task. Source: prd §2.F.AC-NNN / dev-plan T-NNN.tdd_acceptance.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:AcceptanceCriteria',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'acceptance_text': {'name': 'acceptance_text',
                                            'required': True},
                        'entity_id': {'name': 'entity_id',
                                      'pattern': '^AC-[0-9]{3,}$',
                                      'required': True}}})

    acceptance_text: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria']} })
    satisfies: Optional[list[str]] = Field(default=None, description="""This Feature/Component/Task addresses these Requirements.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria', 'Module', 'Component', 'API', 'Page'],
         'inverse': 'satisfied_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^AC-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Module(SoftwareArtifact):
    """
    Architectural module. Source: arch §2 M-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Module',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^M-[0-9]{3,}$',
                                      'required': True}}})

    satisfies: Optional[list[str]] = Field(default=None, description="""This Feature/Component/Task addresses these Requirements.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria', 'Module', 'Component', 'API', 'Page'],
         'inverse': 'satisfied_by'} })
    realized_as: Optional[list[str]] = Field(default=None, description="""Component/Module → Task work-breakdown link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Module', 'Component'], 'inverse': 'realizes'} })
    implements: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Module', 'Component'], 'inverse': 'implemented_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^M-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Component(SoftwareArtifact):
    """
    Architectural sub-component. Binds C-NNN entities sourced from arch docs. ui-spec C-NNN must be remapped to UIComponent UC-NNN via the migration codemod (see task-6 §6.5 #6, task-7 §7.2). UI-route / layout slots remain here as legacy disambiguation but are deprecated for new Component instances; UI fields belong on UIComponent.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Component',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^C-[0-9]{3,}$',
                                      'required': True}}})

    satisfies: Optional[list[str]] = Field(default=None, description="""This Feature/Component/Task addresses these Requirements.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria', 'Module', 'Component', 'API', 'Page'],
         'inverse': 'satisfied_by'} })
    realized_as: Optional[list[str]] = Field(default=None, description="""Component/Module → Task work-breakdown link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Module', 'Component'], 'inverse': 'realizes'} })
    implements: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Module', 'Component'], 'inverse': 'implemented_by'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    ui_route: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Component', 'Page']} })
    layout_spec: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Component', 'Page']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^C-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Interface(SoftwareArtifact):
    """
    Abstract interface contract between modules; non-HTTP siblings of API.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Interface',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^IF-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^IF-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class API(Interface):
    """
    HTTP / RPC contract. Source arch §3 API-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:API',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^API-[0-9]{3,}$',
                                      'required': True}}})

    endpoint_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['API']} })
    http_method: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['API']} })
    request_schema: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['API']} })
    response_schema: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['API']} })
    satisfies: Optional[list[str]] = Field(default=None, description="""This Feature/Component/Task addresses these Requirements.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria', 'Module', 'Component', 'API', 'Page'],
         'inverse': 'satisfied_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^API-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class DataModel(SoftwareArtifact):
    """
    Persistent data entity. Source arch §4 E-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:DataModel',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^E-[0-9]{3,}$',
                                      'required': True}}})

    field_definitions: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['DataModel']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^E-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class ArchitectureDecision(SoftwareArtifact):
    """
    ADR-style decision record. Frontmatter prefix ADR-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:ArchitectureDecision',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^ADR-[0-9]{3,}$'}}})

    rationale: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'ChangeRequest', 'ReviewReport']} })
    decision_outcome: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision']} })
    alternatives: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision']} })
    affects: Optional[list[str]] = Field(default=None, description="""ChangeRequest / ArchitectureDecision impact edge.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'TechStack', 'Risk', 'ChangeRequest'],
         'inverse': 'affected_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^ADR-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class TechStack(SoftwareArtifact):
    """
    Technology-stack declaration anchored to a free-prose section (e.g., arch §1.4). Honors the section heading slug as entity_id when no ID prefix is present; otherwise TS-NNN. Carries narrative content plus structured stack_layers for queryable retrieval. Replaces the source_section() escape hatch for tech-stack content in 0.5.0.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:TechStack',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^TS-[0-9]{3,}$'}}})

    stack_layers: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TechStack']} })
    affects: Optional[list[str]] = Field(default=None, description="""ChangeRequest / ArchitectureDecision impact edge.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'TechStack', 'Risk', 'ChangeRequest'],
         'inverse': 'affected_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^TS-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Screen(SoftwareArtifact):
    """
    Concrete rendered screen, alias of Page.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Screen', 'from_schema': 'https://cataforge.dev/ontology/core'})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })


class Page(Screen):
    """
    UI page; honors P-NNN where the source doc is ui-spec.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Page',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^P-[0-9]{3,}$',
                                      'required': True}}})

    satisfies: Optional[list[str]] = Field(default=None, description="""This Feature/Component/Task addresses these Requirements.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AcceptanceCriteria', 'Module', 'Component', 'API', 'Page'],
         'inverse': 'satisfied_by'} })
    ui_route: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Component', 'Page']} })
    layout_spec: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Component', 'Page']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^P-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Wireframe(SoftwareArtifact):
    """
    Sketch / mock-up; refines a Page.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Wireframe',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^WF-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^WF-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class UIComponent(SoftwareArtifact):
    """
    Reusable UI widget. Distinct from the architecture Component class.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:UIComponent',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^UC-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^UC-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class UserFlow(SoftwareArtifact):
    """
    Sequence of Pages forming a user journey.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:UserFlow',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^UF-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^UF-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Task(SoftwareArtifact):
    """
    Engineering task card. Source dev-plan §3 T-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Task',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^T-[0-9]{3,}$',
                                      'required': True}}})

    task_status: Optional[TaskStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Task']} })
    realizes: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Task'], 'inverse': 'realized_as'} })
    assigned_to_sprint: Optional[str] = Field(default=None, description="""Agile placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_phase: Optional[str] = Field(default=None, description="""Waterfall placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_work_unit: Optional[str] = Field(default=None, description="""Unified accessor (Phase or Sprint or Iteration).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^T-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Subtask(Task):
    """
    Decomposed child of a Task.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Subtask',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^ST-[0-9]{3,}$'}}})

    task_status: Optional[TaskStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Task']} })
    realizes: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Task'], 'inverse': 'realized_as'} })
    assigned_to_sprint: Optional[str] = Field(default=None, description="""Agile placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_phase: Optional[str] = Field(default=None, description="""Waterfall placement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    belongs_to_work_unit: Optional[str] = Field(default=None, description="""Unified accessor (Phase or Sprint or Iteration).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Feature', 'Task']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^ST-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class TestCase(SoftwareArtifact):
    """
    Single verifiable test scenario. Source test-report §2 TC-NNN.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:TestCase',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^TC-[0-9]{3,}$',
                                      'required': True}}})

    verifies: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase', 'TestRun'], 'inverse': 'verified_by'} })
    test_steps: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase']} })
    expected_result: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase']} })
    test_result: Optional[TestResultEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase', 'TestRun']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^TC-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class TestSuite(SoftwareArtifact):
    """
    Grouping of TestCases.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:TestSuite',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^TS-[0-9]{3,}$'}}})

    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^TS-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class TestPlan(SoftwareArtifact):
    """
    Overall test strategy document.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:TestPlan',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^TP-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^TP-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class CoverageRule(SoftwareArtifact):
    """
    Declarative coverage requirement (e.g. every Feature must have ≥1 TestCase).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:CoverageRule',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^CR-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^CR-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class TestRun(SoftwareArtifact):
    """
    A single execution of a TestSuite/TestCase, producing TestResult facts.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:TestRun',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^TR-[0-9]{3,}$'}}})

    test_result: Optional[TestResultEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase', 'TestRun']} })
    verifies: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['TestCase', 'TestRun'], 'inverse': 'verified_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^TR-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Deployment(SoftwareArtifact):
    """
    An act of deploying a Release into an Environment.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Deployment',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^DP-[0-9]{3,}$'}}})

    environment: Optional[EnvironmentEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Deployment']} })
    delivers: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Deployment', 'Release'], 'inverse': 'delivered_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^DP-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Pipeline(SoftwareArtifact):
    """
    CI/CD pipeline definition.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Pipeline',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^PL-[0-9]{3,}$'}}})

    pipeline_steps: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Pipeline']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^PL-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Release(SoftwareArtifact):
    """
    Versioned bundle of delivered Features.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Release',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^REL-[0-9]{3,}$'}}})

    version: Optional[str] = Field(default=None, description="""Semantic version label for releasable artifacts.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Release', 'Document']} })
    release_notes: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Release']} })
    delivers: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Deployment', 'Release'], 'inverse': 'delivered_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^REL-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Environment(SoftwareArtifact):
    """
    Deployment target environment (dev/staging/production).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Environment',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^ENV-[0-9]{3,}$'}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^ENV-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Glossary(SoftwareArtifact):
    """
    Domain term definition.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Glossary',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^GL-[0-9]{3,}$'}}})

    glossary_term: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Glossary']} })
    glossary_definition: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Glossary']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^GL-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Risk(SoftwareArtifact):
    """
    Identified risk plus its mitigation.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Risk',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^RK-[0-9]{3,}$'}}})

    risk_level: Optional[RiskLevelEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Risk']} })
    mitigation: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Risk']} })
    affects: Optional[list[str]] = Field(default=None, description="""ChangeRequest / ArchitectureDecision impact edge.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'TechStack', 'Risk', 'ChangeRequest'],
         'inverse': 'affected_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^RK-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class ChangeRequest(SoftwareArtifact):
    """
    Proposed change with impact set.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:ChangeRequest',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^CHG-[0-9]{3,}$'}}})

    change_status: Optional[ChangeStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ChangeRequest']} })
    rationale: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'ChangeRequest', 'ReviewReport']} })
    affects: Optional[list[str]] = Field(default=None, description="""ChangeRequest / ArchitectureDecision impact edge.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'TechStack', 'Risk', 'ChangeRequest'],
         'inverse': 'affected_by'} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^CHG-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class ReviewReport(SoftwareArtifact):
    """
    Output of a review skill (doc-review / sprint-review / code-review).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:ReviewReport',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^REV-[0-9]{3,}$'}}})

    targets_artifact: Optional[str] = Field(default=None, description="""ReviewReport → the artifact under review.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReviewReport'], 'inverse': 'reviewed_by'} })
    rationale: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'ChangeRequest', 'ReviewReport']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^REV-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class SprintReviewIssue(ReviewReport):
    """
    Issue raised during sprint review. Honors existing SR-NNN prefix.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:SprintReviewIssue',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'entity_id': {'name': 'entity_id',
                                      'pattern': '^SR-[0-9]{3,}$'}}})

    targets_artifact: Optional[str] = Field(default=None, description="""ReviewReport → the artifact under review.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReviewReport'], 'inverse': 'reviewed_by'} })
    rationale: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ArchitectureDecision', 'ChangeRequest', 'ReviewReport']} })
    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    entity_id: str = Field(default=..., description="""Frontmatter ID such as F-001, M-014, T-007.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    priority: Optional[PriorityEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_section: Optional[str] = Field(default=None, description="""Section anchor inside the source doc, e.g. §2.F-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    tags: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    belongs_to_project: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact']} })
    depends_on: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'dependency_of'} })
    dependency_of: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'depends_on'} })
    part_of: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Component'], 'inverse': 'has_part'} })
    has_part: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'TestSuite'], 'inverse': 'part_of'} })
    replaces: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaced_by',
         'slot_uri': 'dcterms:replaces'} })
    replaced_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'],
         'inverse': 'replaces',
         'slot_uri': 'dcterms:isReplacedBy'} })
    was_revision_of: Optional[str] = Field(default=None, description="""PROV revision link between two snapshots of the same logical entity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'slot_uri': 'prov:wasRevisionOf'} })
    reviewed_by: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'targets_artifact'} })
    located_in_section: Optional[str] = Field(default=None, description="""SoftwareArtifact → the Section it was sourced from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact'], 'inverse': 'contains_entity'} })

    @field_validator('entity_id')
    def pattern_entity_id(cls, v):
        pattern=re.compile(r"^SR-[0-9]{3,}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entity_id format: {v}"
            raise ValueError(err_msg)
        return v


class Document(ConfiguredBaseModel):
    """
    A whole business document; container for its volumes, sections, and entities.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Document',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'id': {'name': 'id', 'required': True},
                        'title': {'name': 'title', 'required': True}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    doc_type: Optional[str] = Field(default=None, description="""doc_type of a Document, e.g. prd / arch.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    version: Optional[str] = Field(default=None, description="""Semantic version label for releasable artifacts.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Release', 'Document']} })
    status: Optional[ArtifactStatusEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    source_path: Optional[str] = Field(default=None, description="""Project-root-relative posix path of a Document's source file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    frontmatter_raw: Optional[str] = Field(default=None, description="""Verbatim frontmatter block of a Document's source file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    preamble_body: Optional[str] = Field(default=None, description="""Document body before the first §-level heading (H1 line and lead prose).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    authored_by: Optional[str] = Field(default=None, description="""Free-form attribution (role name or username); not coupled to governance namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document']} })
    created_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    updated_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document']} })
    has_volume: Optional[list[str]] = Field(default=None, description="""Document → its split volumes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    has_section: Optional[list[str]] = Field(default=None, description="""Document / Volume → its sections.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Volume']} })


class Volume(ConfiguredBaseModel):
    """
    A split volume of a Document (honors split_from / volume_type).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Volume',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'id': {'name': 'id', 'required': True}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    volume_type: Optional[str] = Field(default=None, description="""Split-volume kind, e.g. features / modules / sprint.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Volume']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    part_of_document: Optional[str] = Field(default=None, description="""Volume / Section → the document it belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Volume', 'Section']} })
    has_section: Optional[list[str]] = Field(default=None, description="""Document / Volume → its sections.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Volume']} })


class Section(ConfiguredBaseModel):
    """
    Heading-delimited section of a Document/Volume. Carries narrative prose (narrative_body) and the structured entities sourced from it (contains_entity), making whole-document content — structured and prose — first-class graph content.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'cf:Section',
         'from_schema': 'https://cataforge.dev/ontology/core',
         'slot_usage': {'id': {'name': 'id', 'required': True}}})

    id: str = Field(default=..., description="""URI; instances live under cfprj namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Project', 'Document', 'Volume', 'Section']} })
    section_anchor: Optional[str] = Field(default=None, description="""Section anchor inside its document, e.g. §2.M-001.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    narrative_body: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    sort_key: str = Field(default=..., description="""Deterministic export sort key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    position: Optional[str] = Field(default=None, description="""Zero-padded document-order index of a Section for whole-document reconstruction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    section_level: Optional[str] = Field(default=None, description="""Heading depth of a Section; level-2 sections tile-cover the document body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    content_hash: Optional[str] = Field(default=None, description="""SHA-256 of the source Markdown section, mirrors .doc-index.json content_hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Section']} })
    source_doc: Optional[str] = Field(default=None, description="""Relative path of the Markdown file the entity was exported from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SoftwareArtifact', 'Document', 'Volume', 'Section']} })
    part_of_document: Optional[str] = Field(default=None, description="""Volume / Section → the document it belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Volume', 'Section']} })
    part_of_volume: Optional[str] = Field(default=None, description="""Section → the volume it belongs to (when the document is split).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    contains_entity: Optional[list[str]] = Field(default=None, description="""Section → the structured entities sourced from it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section'], 'inverse': 'located_in_section'} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
SoftwareArtifact.model_rebuild()
Project.model_rebuild()
WorkUnit.model_rebuild()
Phase.model_rebuild()
Sprint.model_rebuild()
Iteration.model_rebuild()
Milestone.model_rebuild()
Requirement.model_rebuild()
Feature.model_rebuild()
UserStory.model_rebuild()
Epic.model_rebuild()
AcceptanceCriteria.model_rebuild()
Module.model_rebuild()
Component.model_rebuild()
Interface.model_rebuild()
API.model_rebuild()
DataModel.model_rebuild()
ArchitectureDecision.model_rebuild()
TechStack.model_rebuild()
Screen.model_rebuild()
Page.model_rebuild()
Wireframe.model_rebuild()
UIComponent.model_rebuild()
UserFlow.model_rebuild()
Task.model_rebuild()
Subtask.model_rebuild()
TestCase.model_rebuild()
TestSuite.model_rebuild()
TestPlan.model_rebuild()
CoverageRule.model_rebuild()
TestRun.model_rebuild()
Deployment.model_rebuild()
Pipeline.model_rebuild()
Release.model_rebuild()
Environment.model_rebuild()
Glossary.model_rebuild()
Risk.model_rebuild()
ChangeRequest.model_rebuild()
ReviewReport.model_rebuild()
SprintReviewIssue.model_rebuild()
Document.model_rebuild()
Volume.model_rebuild()
Section.model_rebuild()
