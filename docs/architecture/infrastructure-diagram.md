# Infrastructure Diagram & Security Threat Modeling

## Infrastructure Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Internet / Public                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │   CloudFlare / WAF      │
                    │  • DDoS Protection      │
                    │  • Rate Limiting        │
                    │  • SSL Termination      │
                    └─────────────┬───────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Load Balancer          │
                    │  • Health Checks         │
                    │  • SSL Termination       │
                    │  • Request Routing      │
                    └─────────────┬───────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
┌───────▼────────┐      ┌─────────▼────────┐      ┌────────▼────────┐
│  API Gateway   │      │  API Gateway     │      │  API Gateway    │
│  (Zone 1)      │      │  (Zone 2)        │      │  (Zone 3)       │
│  • Kong        │      │  • Kong          │      │  • Kong         │
│  • Rate Limit  │      │  • Rate Limit    │      │  • Rate Limit   │
│  • Auth        │      │  • Auth          │      │  • Auth         │
└───────┬────────┘      └─────────┬────────┘      └────────┬────────┘
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │   Private VPC            │
                    │   (10.0.0.0/16)          │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Public Subnet      │  │
                    │  │  (10.0.1.0/24)      │  │
                    │  │  • API Gateway      │  │
                    │  │  • Load Balancer    │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Application Subnet  │  │
                    │  │  (10.0.2.0/24)      │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Decision      │  │  │
                    │  │  │ Service       │  │  │
                    │  │  │ (K8s Pods)    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Document      │  │  │
                    │  │  │ Service       │  │  │
                    │  │  │ (K8s Pods)    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Celery        │  │  │
                    │  │  │ Workers       │  │  │
                    │  │  │ (K8s Pods)    │  │  │
                    │  │  └───────────────┘  │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Data Subnet        │  │
                    │  │  (10.0.3.0/24)      │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ PostgreSQL   │  │  │
                    │  │  │ Primary      │  │  │
                    │  │  │ (Encrypted)  │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ PostgreSQL   │  │  │
                    │  │  │ Replica 1    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ PostgreSQL   │  │  │
                    │  │  │ Replica 2    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ PostgreSQL   │  │  │
                    │  │  │ Replica 3    │  │  │
                    │  │  └───────────────┘  │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Cache Subnet       │  │
                    │  │  (10.0.4.0/24)      │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Redis         │  │  │
                    │  │  │ Primary       │  │  │
                    │  │  │ (Sentinel)    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Redis         │  │  │
                    │  │  │ Replica       │  │  │
                    │  │  └───────────────┘  │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Storage Subnet     │  │
                    │  │  (10.0.5.0/24)      │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ S3 / MinIO    │  │  │
                    │  │  │ (Encrypted)   │  │  │
                    │  │  └───────────────┘  │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Monitoring Subnet  │  │
                    │  │  (10.0.6.0/24)      │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Prometheus    │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ Grafana       │  │  │
                    │  │  └───────────────┘  │  │
                    │  │                     │  │
                    │  │  ┌───────────────┐  │  │
                    │  │  │ ELK Stack      │  │  │
                    │  │  │ (Logging)      │  │  │
                    │  │  └───────────────┘  │  │
                    │  └─────────────────────┘  │
                    └───────────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │   External Services       │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │ AWS Textract        │  │
                    │  │ (OCR Tier 3)       │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │ OAuth Provider      │  │
                    │  │ (Auth0 / Okta)     │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │ PagerDuty          │  │
                    │  │ (Alerts)           │  │
                    │  └─────────────────────┘  │
                    └───────────────────────────┘
```

## Network Security

### Security Groups / Firewall Rules

#### API Gateway Security Group
- **Inbound**: 
  - Port 443 (HTTPS) from Load Balancer
  - Port 80 (HTTP) from Load Balancer (redirect to 443)
- **Outbound**:
  - Port 8000-8001 to Application Subnet (Decision/Document Services)

#### Application Subnet Security Group
- **Inbound**:
  - Port 8000-8001 from API Gateway
  - Port 5432 from Data Subnet (PostgreSQL)
  - Port 6379 from Cache Subnet (Redis)
- **Outbound**:
  - Port 443 to External Services (HTTPS)
  - Port 5432 to Data Subnet (PostgreSQL)
  - Port 6379 to Cache Subnet (Redis)
  - Port 9000 to Storage Subnet (S3/MinIO)

#### Data Subnet Security Group
- **Inbound**:
  - Port 5432 from Application Subnet only
- **Outbound**:
  - Port 5432 for replication (between primary and replicas)

#### Cache Subnet Security Group
- **Inbound**:
  - Port 6379 from Application Subnet only
- **Outbound**:
  - Port 6379 for replication (Redis Sentinel)

#### Storage Subnet Security Group
- **Inbound**:
  - Port 9000 from Application Subnet only
- **Outbound**: None

## Security Threat Modeling

### STRIDE Analysis

#### 1. Spoofing Identity

**Threat**: Attacker impersonates legitimate user or service

**Attack Vectors**:
- Stolen JWT tokens
- API key compromise
- Service-to-service authentication bypass

**Mitigations**:
- JWT tokens with short expiry (1 hour)
- Refresh tokens with longer expiry (7 days)
- API keys rotated every 90 days
- Service-to-service authentication with mTLS
- Rate limiting to prevent brute force
- Audit logging of all authentication attempts

**Detection**:
- Monitor for unusual authentication patterns
- Alert on multiple failed login attempts
- Track token usage patterns

#### 2. Tampering with Data

**Threat**: Unauthorized modification of data

**Attack Vectors**:
- SQL injection
- Man-in-the-middle attacks
- Unauthorized API requests
- Database compromise

**Mitigations**:
- Parameterized queries (SQLAlchemy ORM)
- Input validation (Pydantic models)
- TLS 1.3 for all communications
- Database encryption at rest (AES-256)
- Immutable audit logs
- Role-based access control (RBAC)
- API request signing

**Detection**:
- Database change monitoring
- Audit log analysis
- Unusual data modification patterns

#### 3. Repudiation

**Threat**: User denies performing an action

**Attack Vectors**:
- Deletion of audit logs
- Modification of audit logs
- Lack of audit trail

**Mitigations**:
- Immutable audit logs (write-only, 7-year retention)
- All actions logged with user ID, timestamp, IP address
- Decision history cannot be deleted
- Audit logs stored in separate, encrypted database
- Regular audit log backups

**Detection**:
- Audit log integrity checks
- Regular audit log reviews
- Alert on audit log access attempts

#### 4. Information Disclosure

**Threat**: Unauthorized access to sensitive data

**Attack Vectors**:
- Database breach
- Unencrypted data in transit
- Unencrypted data at rest
- Log file exposure
- API response containing sensitive data

**Mitigations**:
- Encryption at rest (AES-256) for database and S3
- Encryption in transit (TLS 1.3)
- PII tokenization for sensitive fields
- Data masking in logs and non-production environments
- Least privilege access (RBAC)
- Network segmentation (private subnets)
- Database connection encryption
- S3 bucket policies (private, encrypted)

**Detection**:
- Data access monitoring
- Unusual query patterns
- Large data exports
- Access from unusual locations

#### 5. Denial of Service (DoS)

**Threat**: Service unavailable due to resource exhaustion

**Attack Vectors**:
- DDoS attacks
- Resource exhaustion (CPU, memory, connections)
- Database connection pool exhaustion
- Rate limit bypass

**Mitigations**:
- DDoS protection (CloudFlare / AWS Shield)
- Rate limiting (1000 requests/minute per user)
- Connection pooling (max 100 connections per service)
- Auto-scaling for traffic spikes
- Circuit breakers for external services
- Resource limits (CPU, memory) per pod
- Database connection pooling
- Queue depth monitoring and alerts

**Detection**:
- Traffic spike monitoring
- Resource usage alerts
- Response time degradation
- Error rate spikes

#### 6. Elevation of Privilege

**Threat**: Unauthorized access to privileged functions

**Attack Vectors**:
- Privilege escalation
- Role manipulation
- Bypass of authorization checks
- Service account compromise

**Mitigations**:
- Role-based access control (RBAC)
- Principle of least privilege
- Regular access reviews
- Service accounts with minimal permissions
- Separation of duties (analyst vs. admin)
- Authorization checks at every endpoint
- Audit logging of privilege changes

**Detection**:
- Unusual privilege escalation attempts
- Access to unauthorized resources
- Role change monitoring

## Security Controls Matrix

| Control | Implementation | Status |
|---------|---------------|--------|
| Authentication | OAuth 2.0 / JWT | ✅ |
| Authorization | RBAC (Analyst, Admin, Auditor) | ✅ |
| Encryption at Rest | AES-256 (Database, S3) | ✅ |
| Encryption in Transit | TLS 1.3 | ✅ |
| Network Segmentation | Private VPC, Security Groups | ✅ |
| DDoS Protection | CloudFlare / AWS Shield | ✅ |
| Rate Limiting | API Gateway (1000 req/min) | ✅ |
| Input Validation | Pydantic models | ✅ |
| SQL Injection Prevention | Parameterized queries | ✅ |
| Audit Logging | Immutable logs, 7-year retention | ✅ |
| PII Protection | Tokenization, data masking | ✅ |
| Secret Management | AWS KMS / HashiCorp Vault | ✅ |
| Vulnerability Scanning | Regular scans, dependency updates | ✅ |
| Penetration Testing | Annual third-party testing | ✅ |
| Incident Response | Runbooks, 24/7 on-call | ✅ |

## Security Monitoring & Alerting

### Security Alerts

1. **Authentication Failures**
   - > 5 failed attempts in 5 minutes
   - Unusual IP addresses
   - Token validation failures

2. **Authorization Failures**
   - Access denied to resources
   - Privilege escalation attempts
   - Unauthorized API calls

3. **Data Access Anomalies**
   - Large data exports
   - Unusual query patterns
   - Access from unusual locations
   - Off-hours access

4. **Network Anomalies**
   - Port scanning attempts
   - Unusual traffic patterns
   - DDoS attack detection

5. **System Compromise Indicators**
   - Unusual process execution
   - File system changes
   - Configuration modifications
   - Audit log tampering attempts

## Compliance & Governance

### Data Protection
- **Encryption**: AES-256 at rest, TLS 1.3 in transit
- **Access Control**: RBAC, least privilege
- **Data Retention**: 7 years (compliance requirement)
- **Data Deletion**: Secure deletion after retention period

### Audit & Compliance
- **Audit Logs**: All data access logged
- **Compliance Reports**: Monthly reports
- **Access Reviews**: Quarterly access reviews
- **Penetration Testing**: Annual third-party testing

### Incident Response
- **Response Time**: < 1 hour for critical incidents
- **Communication**: PagerDuty alerts, Slack notifications
- **Documentation**: Incident runbooks
- **Post-Incident**: Root cause analysis, remediation

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [AWS Security Best Practices](https://aws.amazon.com/security/security-resources/)
- [Kubernetes Security](https://kubernetes.io/docs/concepts/security/)

