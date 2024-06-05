import json
from datetime import datetime
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from fhir.resources.auditevent import AuditEvent, AuditEventAgent, AuditEventSource, AuditEventEntity, AuditEventOutcome
from fhir.resources.coding import Coding
from fhir.resources.reference import Reference
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.identifier import Identifier
from fhir.resources.auditevent import AuditEventEntityDetail
from datetime import datetime


def create_audit_event(payload):
    current_time = datetime.now().isoformat() + 'Z'  # HL7 prefers timestamps in UTC with a 'Z' suffix

    # Create the event type coding
    event_type = CodeableConcept(
        coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/audit-event-type",
            code="110110",  # Example code for Orthanc resource authorization
            display=payload.get('event', 'Orthanc Resource Authorization')
        )]
    )

    # Define the agent (user)
    user_value = str(payload.get('user')).strip()
    if not user_value:
        raise ValueError("User value cannot be empty")

    agent_user = AuditEventAgent(
        who=Reference(
            identifier=Identifier(
                value=user_value
            ),
            display=user_value
        ),
        requestor=True,
    )

    # Optionally, you can add more agents like the system agent
    agent_system = AuditEventAgent(
        who=Reference(
            display="Sonador Web Application"
        ),
        requestor=False
    )

    # Define the source of the event
    source = AuditEventSource(
        observer=Reference(
            display="Sonador Web Application"
        ),
        site=Reference(
            display="Web Server"
        ),
        type=[CodeableConcept(
            coding=[Coding(
                system="http://terminology.hl7.org/CodeSystem/security-source-type",
                code="4",  # 4 represents an application
                display="Application"
            )]
        )]
    )

    # Define the entity involved in the event
    orthanc_id_value = str(payload.get('orthanc_id', '')).strip()
    entity_reference = None
    if orthanc_id_value:
        entity_reference = Reference(
            identifier=Identifier(
                value=orthanc_id_value,
                type=CodeableConcept(
                    coding=[Coding(
                        system="http://terminology.hl7.org/CodeSystem/identifier-type",
                        code="ORTH",
                        display="Orthanc UID"
                    )],
                    text="Orthanc UID"
                )
                
            )
        )

    def create_audit_event_entity_detail(type_text, value):
        if value:
            return AuditEventEntityDetail(
                type=CodeableConcept(text=type_text),
                valueString=value
            )
        return None

    entity_details = [
        create_audit_event_entity_detail("Token expiration", f"{payload.get('validity')} minutes"),
        create_audit_event_entity_detail("Access Level", payload.get('level', 'system')),
        create_audit_event_entity_detail("Method", payload.get('method', '')),
        create_audit_event_entity_detail("DICOM UID", payload.get('dicom_uid', '')),
        create_audit_event_entity_detail("URI", payload.get('uri', '')),
        create_audit_event_entity_detail("Authorization Granted", str(payload.get('granted')))
    ]
    entity_details = [detail for detail in entity_details if detail is not None]

    entity = AuditEventEntity(
        what=entity_reference,
        role=CodeableConcept(
            coding=[Coding(
                code="2",
                display="Session"
            )]
        ),
        securityLabel=[CodeableConcept(
            coding=[Coding(
                code="1",
                display="Confidential"
            )]
        )],
        detail=entity_details
    )

    # Create the outcome
    outcome = AuditEventOutcome(
        code=Coding(
            system="http://hl7.org/fhir/audit-event-outcome",
            code="0" if payload.get('granted') else "4",  # 0 for success, 4 for failure
            display="Success" if payload.get('granted') else "Failure"
        ),
        detail=[CodeableConcept(text="Authorization success" if payload.get('granted') else "Authorization failure")]
    )

    # Create the AuditEvent
    audit_event = AuditEvent(
        category=[event_type],
        code=event_type,
        action=payload.get('method', 'GET')[0].upper(),
        recorded=current_time,  # Timestamp in UTC
        outcome=outcome,
        agent=[agent_user, agent_system],
        source=source,
        entity=[entity]
    )
    return audit_event


class KafkaManager:
    '''https://docs.confluent.io/kafka-clients/python/current/overview.html
    '''
    def __init__(self, bootstrap_servers, client_id):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.producer = None
        self.admin_client = None

    def get_producer(self):
        if not self.producer:
            self.producer = Producer({
                'bootstrap.servers': self.bootstrap_servers,
                'client.id': self.client_id
            })
        return self.producer

    def get_admin_client(self):
        if not self.admin_client:
            self.admin_client = AdminClient({
                'bootstrap.servers': self.bootstrap_servers,
                'client.id': self.client_id
            })
        return self.admin_client

    def create_topic(self, topic_name, num_partitions=1, replication_factor=1):
        admin_client = self.get_admin_client()
        topics = admin_client.list_topics().topics
        if topic_name in topics:
            print(f"Topic '{topic_name}' already exists.")
            return False
        else:
            topic_list = [NewTopic(topic_name, num_partitions, replication_factor)]
            try:
                admin_client.create_topics(topic_list)
                print(f"Topic '{topic_name}' created successfully.")
                return True
            except Exception as e:
                print(f"Failed to create topic '{topic_name}': {e}")
                return False

    def send_audit_event(self, topic, data):
        audit_event_json = create_audit_event(data).json()
        self.send_message(topic, audit_event_json)

    def send_message(self, topic, message):
        producer = self.get_producer()
        producer.produce(topic, json.dumps(message).encode('utf-8'))
        producer.flush()