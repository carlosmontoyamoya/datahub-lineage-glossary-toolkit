import json
import time
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
    ChangeTypeClass
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

for item in glossary_terms:
    term_name = item["term"]
    description = item["description"]
    field = item["field"]
    db = item["database"]
    table = item["table"]
    platform = item["platform"]
    env = item["env"]

    dataset_name = f"{db}.{table}"
    dataset_urn = make_dataset_urn(platform, dataset_name, env)
    field_urn = f"urn:li:datasetField:({dataset_urn},{field})"
    term_urn = make_term_urn(term_name)

    # 1. Crear o actualizar el término del glosario
    term_info = GlossaryTermInfoClass(
        name=term_name,
        definition=description,
        termSource=""
    )
    term_mcp = MetadataChangeProposalWrapper(
        entityType="glossaryTerm",
        changeType=ChangeTypeClass.UPSERT,
        entityUrn=term_urn,
        aspect=term_info
    )
    rest_emitter.emit(term_mcp)
    print(f"✅ Término creado o actualizado: {term_name}")

    # 2. Asignar owner al término
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

    # 3. Asociar el término al campo del dataset
    assoc = GlossaryTermAssociationClass(urn=term_urn)
    glossary_terms_aspect = GlossaryTermsClass(
        terms=[assoc],
        auditStamp=AuditStampClass(
            time=int(time.time() * 1000),
            actor=actor_urn
        )
    )
    assoc_mcp = MetadataChangeProposalWrapper(
        entityType="datasetField",
        entityUrn=field_urn,
        changeType=ChangeTypeClass.UPSERT,
        aspect=glossary_terms_aspect,
        aspectName="glossaryTerms",
        systemMetadata=SystemMetadataClass(
            lastObserved=int(time.time() * 1000),
            runId="manual-glossary-ingestion"
        )
    )
    rest_emitter.emit(assoc_mcp)
    print(f"🔗 Asociado '{term_name}' a {dataset_name}.{field}")

    # 4. Asociar también el término al dataset completo (no solo a la columna)
    assoc_dataset = GlossaryTermAssociationClass(urn=term_urn)
    glossary_terms_dataset = GlossaryTermsClass(
        terms=[assoc_dataset],
        auditStamp=AuditStampClass(
            time=int(time.time() * 1000),
            actor=actor_urn
        )
    )
    assoc_dataset_mcp = MetadataChangeProposalWrapper(
        entityType="dataset",
        entityUrn=dataset_urn,
        changeType=ChangeTypeClass.UPSERT,
        aspect=glossary_terms_dataset,
        aspectName="glossaryTerms",
        systemMetadata=SystemMetadataClass(
            lastObserved=int(time.time() * 1000),
            runId="manual-glossary-ingestion"
        )
    )
    rest_emitter.emit(assoc_dataset_mcp)
    print(f"📦 Asociado '{term_name}' también al dataset completo: {dataset_name}")

