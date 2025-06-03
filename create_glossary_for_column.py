import json
import time
from collections import defaultdict
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    GlossaryTermInfoClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    OwnershipClass,
    OwnerClass,
    OwnershipTypeClass,
    AuditStampClass,
    SystemMetadataClass,
    ChangeTypeClass,
    EditableSchemaMetadataClass,
    EditableSchemaFieldInfoClass
)
from datahub.emitter.mce_builder import make_term_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper

# Cargar configuración
with open("config.json") as f:
    config = json.load(f)

gms_endpoint = f"{config['api_url']}/api/gms"
access_token = config["access_token"]
actor_urn = "urn:li:corpuser:ecigoyeneche@arkho.io"

rest_emitter = DatahubRestEmitter(
    gms_server=gms_endpoint,
    token=access_token
)

# Cargar definiciones de glosario
with open("glossary_terms.json") as f:
    glossary_terms = json.load(f)

# Agrupar EditableSchemaFieldInfo por dataset_urn
dataset_fields_map = defaultdict(list)

for item in glossary_terms:
    term_name = item["term"]
    description = item["description"]
    field_name = item["field"]

    term_urn = make_term_urn(term_name)
    dataset_urn = make_dataset_urn(item["platform"], f"{item['database']}.{item['table']}", item["env"])

    # 1. Crear término
    term_info = GlossaryTermInfoClass(
        name=term_name,
        definition=description,
        termSource=""
    )
    term_mcp = MetadataChangeProposalWrapper(
        entityType="glossaryTerm",
        entityUrn=term_urn,
        changeType=ChangeTypeClass.UPSERT,
        aspect=term_info
    )
    rest_emitter.emit(term_mcp)
    print(f"✅ Término creado o actualizado: {term_name}")

    # 2. Asignar owner
    ownership = OwnershipClass(
        owners=[
            OwnerClass(
                owner=actor_urn,
                type=OwnershipTypeClass.DATAOWNER
            )
        ],
        lastModified=AuditStampClass(
            time=int(time.time() * 1000),
            actor=actor_urn
        )
    )
    owner_mcp = MetadataChangeProposalWrapper(
        entityType="glossaryTerm",
        entityUrn=term_urn,
        changeType=ChangeTypeClass.UPSERT,
        aspect=ownership,
        aspectName="ownership"
    )
    rest_emitter.emit(owner_mcp)
    print(f"👤 Owner asignado al término: {term_name}")

    # 3. Acumular campo editable
    field_info = EditableSchemaFieldInfoClass(
        fieldPath=field_name,
        glossaryTerms=GlossaryTermsClass(
            terms=[GlossaryTermAssociationClass(urn=term_urn)],
            auditStamp=AuditStampClass(
                time=int(time.time() * 1000),
                actor=actor_urn
            )
        )
    )
    dataset_fields_map[dataset_urn].append(field_info)

# Emitir UN solo editableSchemaMetadata por dataset
for dataset_urn, field_infos in dataset_fields_map.items():
    editable_schema = EditableSchemaMetadataClass(
        editableSchemaFieldInfo=field_infos
    )

    assoc_mcp = MetadataChangeProposalWrapper(
        entityType="dataset",
        entityUrn=dataset_urn,
        changeType=ChangeTypeClass.UPSERT,
        aspect=editable_schema,
        aspectName="editableSchemaMetadata",
        systemMetadata=SystemMetadataClass(
            lastObserved=int(time.time() * 1000),
            runId="manual-glossary-association"
        )
    )

    rest_emitter.emit(assoc_mcp)
    print(f"🧩 Enviado editableSchemaMetadata para dataset: {dataset_urn}")
