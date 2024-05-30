import json
from datetime import datetime
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from fhir.resources.auditevent import AuditEvent, AuditEventAgent, AuditEventSource, AuditEventEntity
from fhir.resources.fhirtypes import CodingType, ReferenceType
from datetime import datetime

def create_audit_event(payload):
    current_time = datetime.utcnow().isoformat() + 'Z'  # HL7 prefers timestamps in UTC with a 'Z' suffix

    # Create the event type coding
    event_type = CodingType({
        "system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
        "code": "110110",  # Example code for Orthanc resource authorization
        "display": "Orthanc Resource Authorization"
    })

    # Define the agent (user)
    agent_user = AuditEventAgent({
        "who": ReferenceType({
            "identifier": {
                "value": payload.get('user')
            },
            "display": payload.get('user')
        }),
        "network": {
            "address": payload.get('ip_address', 'unknown'),
            "type": "2"  # 2 represents an IP address
        },
        "requestor": True
    })

    # Optionally, you can add more agents like the system agent
    agent_system = AuditEventAgent({
        "who": ReferenceType({
            "display": "Django Application"
        }),
        "requestor": False
    })

    # Define the source of the event
    source = AuditEventSource({
        "site": "Web Server",
        "observer": ReferenceType({
            "display": "Django Application"
        })
    })

    # Define the entity involved in the event
    entity = AuditEventEntity({
        "what": ReferenceType({
            "identifier": {
                "value": payload.get('orthanc_id', '')
            }
        }),
        "type": CodingType({
            "code": "2",
            "display": "Session"
        }),
        "description": "User session identifier",
        "detail": [
            {
                "type": "Token expiration",
                "valueString": f"{payload.get('validity')} minutes"
            },
            {
                "type": "Access Level",
                "valueString": payload.get('level', 'system')
            },
            {
                "type": "Method",
                "valueString": payload.get('method', '')
            },
            {
                "type": "DICOM UID",
                "valueString": payload.get('dicom_uid', '')
            },
            {
                "type": "URI",
                "valueString": payload.get('uri', '/dicom-web/studies')
            },
            {
                "type": "Authorization Granted",
                "valueString": str(payload.get('granted', ''))
            }
        ]
    })

    # Create the AuditEvent
    audit_event = AuditEvent({
        "type": event_type,
        "subtype": [CodingType({
            "system": "http://hl7.org/fhir/restful-interaction",
            "code": payload.get('method').lower(),
            "display": payload.get('method').upper()
        })],
        "action": payload.get('method')[0].upper(),
        "recorded": current_time,  # Timestamp in UTC
        "outcome": "0" if payload.get('granted') else "4",  # 0 for success, 4 for failure
        "outcomeDesc": "Authorization success" if payload.get('granted') else "Authorization failure",
        "agent": [agent_user, agent_system],
        "source": source,
        "entity": [entity]
    })

    return audit_event

# Example usage
payload = {
    'event': 'orthanc_resource_authorization',
    'orthanc_id': 'orthanc12345',
    'method': 'GET',
    'level': 'system',
    'dicom_uid': 'unique_dicom_uid',
    'uri': '/dicom-web/studies',
    'user': 'john_doe',
    'granted': True,
    'validity': 30,
    'ip_address': '192.168.1.1'  # Assuming you have this information
}

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
        audit_event_json = create_audit_event(data)
        self.send_message(topic, audit_event_json)

    def send_message(self, topic, message):
        producer = self.get_producer()
        producer.produce(topic, json.dumps(message).encode('utf-8'))
        producer.flush()