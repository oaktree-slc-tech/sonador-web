import json
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
from datetime import datetime

def generate_hl7_audit_event(form_data, username, expiration_minutes):
    current_time = datetime.now().isoformat() + 'Z'  # HL7 prefers timestamps in UTC with a 'Z' suffix
    return {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
            "code": "110100",
            "display": "User Authentication"
        },
        "action": "E",
        "recorded": current_time,
        "outcome": "0",  # Assuming success; use '4' or other appropriate codes for failures
        "outcomeDesc": "Authentication success",
        "agent": [
            {
                "who": {
                    "identifier": {
                        "value": username
                    }
                },
                "altId": "User ID",
                "network": {
                    "address": form_data.get('token_value', 'unknown'),
                    "type": "5"
                },
                "purposeOfUse": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ActReason",
                                "code": "HOPERAT",
                                "display": "Operational Use"
                            }
                        ]
                    }
                ]
            }
        ],
        "source": {
            "site": "Sonador Platform",
            "identifier": {
                "value": "Sonador Web Application" 
            },
            "type": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/security-source-type",
                    "code": "4",  # Code '4' represents an application
                    "display": "Application"
                }
            ],
            "observer": {
                "reference": form_data.get('dicom_uid', ''),
                "display": "DICOM Study UID"
            }
        },
        "entity": [
            {
                "what": {
                    "identifier": {
                        "value": form_data.get('session', 'unknown')
                    }
                },
                "type": {
                    "code": "2",
                    "display": "Session"
                },
                "description": "User session identifier",
                "detail": [
                    {
                        "type": "Token expiration",
                        "valueString": f"{expiration_minutes} minutes"
                    },
                    {
                        "type": "Access Level",
                        "valueString": form_data.get('level', '')
                    },
                    {
                        "type": "Method",
                        "valueString": form_data.get('method', '')
                    },
                    {
                        "type": "DICOM UID",
                        "valueString": form_data.get('dicom_uid', '')
                    },
                    {
                        "type": "Orthanc ID",
                        "valueString": form_data.get('orthanc_id', '')
                    },
                    {
                        "type": "URI",
                        "valueString": form_data.get('uri', '')
                    }
                ]
            }
        ]
    }



class KafkaManager:
    def __init__(self, bootstrap_servers, client_id):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.producer = None
        self.admin_client = None

    def get_producer(self):
        if not self.producer:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        return self.producer

    def get_admin_client(self):
        if not self.admin_client:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id
            )
        return self.admin_client

    def create_topic(self, topic_name, num_partitions=1, replication_factor=1):
        admin_client = self.get_admin_client()
        topics = admin_client.list_topics()
        if topic_name in topics:
            print(f"Topic '{topic_name}' already exists.")
            return False
        else:
            topic_list = [NewTopic(name=topic_name, num_partitions=num_partitions, replication_factor=replication_factor)]
            try:
                admin_client.create_topics(new_topics=topic_list, validate_only=False)
                print(f"Topic '{topic_name}' created successfully.")
                return True
            except TopicAlreadyExistsError:
                print(f"Topic '{topic_name}' already exists.")
                return False
            
    def send_audit_event(self, topic, form_data, username, expiration_minutes):
        audit_event_json = generate_hl7_audit_event(form_data, username, expiration_minutes)
        self.send_message(topic, audit_event_json)

    def send_message(self, topic, message):
        producer = self.get_producer()
        producer.send(topic, message)
        producer.flush()

    def consume_messages(self, topic, group_id):
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset='earliest',
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        for message in consumer:
            print(f"Received message: {message.value}")
