# AFAS-link

Automatische koppeling tussen **AFAS Profit** (HR/ERP) en **Microsoft Entra ID** (Azure AD) en/of **on-premises Active Directory**.

AFAS-link pollt periodiek de AFAS REST API, detecteert wijzigingen in medewerkergegevens en voert automatisch gebruikersprovisioning, -updates en -deprovisioning uit in uw directoryomgeving.

---

## Functionaliteiten

- **Automatische provisioning**: Nieuwe medewerkers in AFAS krijgen automatisch een Entra ID- en/of AD-account
- **Incrementele synchronisatie**: Wijzigingen in naam, functie, afdeling worden direct doorgevoerd
- **Deprovisioning**: Bij uitdiensttreding worden licenties ingetrokken, groepslidmaatschappen verwijderd en accounts uitgeschakeld
- **E-mailadresgeneratie**: Configureerbare patronen met automatische deduplicatie
- **Groepstoewijzingen**: Automatisch op basis van afdeling, functie of andere AFAS-velden
- **OU-beheer (AD)**: Automatische plaatsing in de juiste Organizational Unit
- **Webdashboard**: Overzicht van synchronisatiestatus, medewerkers en audit-logs
- **Multi-omgeving**: Ondersteuning voor meerdere AFAS-omgevingen tegelijk
- **Demo-modus**: Volledig testbaar zonder echte API-credentials

---

## Vereisten

- Python 3.11+
- AFAS Profit REST API-toegang met een geldig token
- Microsoft Entra ID app-registratie (met `User.ReadWrite.All`, `Group.ReadWrite.All` permissies)
- (Optioneel) On-premises Active Directory met een serviceaccount

---

## Snelstart (demo-modus)

```bash
# 1. Repository klonen
git clone <repository-url>
cd AFAS-link

# 2. Afhankelijkheden installeren
pip install -r requirements.txt

# 3. Configuratiebestanden aanmaken
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# 4. Database vullen met demo-data
python scripts/seed_demo.py

# 5. Applicatie starten
uvicorn src.main:app --reload

# Dashboard bereikbaar op: http://localhost:8000
```

---

## Productie-installatie

### 1. Omgevingsvariabelen instellen

Kopieer `.env.example` naar `.env` en vul de vereiste waarden in:

```bash
cp .env.example .env
```

Bewerk `.env`:

```dotenv
DEMO_MODE=false
DATABASE_URL=sqlite:///./afas_link.db

# AFAS token (het <data>-gedeelte uit het token-XML)
AFAS_ENV1_TOKEN=uw_afas_token_hier

# Microsoft Entra ID
ENTRA_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ENTRA_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ENTRA_CLIENT_SECRET=uw_client_secret_hier

# Active Directory (indien van toepassing)
AD_BIND_PASSWORD=uw_serviceaccount_wachtwoord
```

### 2. Configuratiebestand instellen

Kopieer `config/config.example.yaml` naar `config/config.yaml` en pas aan:

```bash
cp config/config.example.yaml config/config.yaml
```

Minimale configuratie:

```yaml
environments:
  - name: "Mijn Bedrijf BV"
    environment_nr: "12345"       # Uw AFAS-omgevingsnummer
    token_env_var: "AFAS_ENV1_TOKEN"
    enabled: true
    sync_interval_minutes: 15

entra_id:
  tenant_id: "${ENTRA_TENANT_ID}"
  client_id: "${ENTRA_CLIENT_ID}"
  client_secret: "${ENTRA_CLIENT_SECRET}"
  domain: "uwbedrijf.nl"
  licenses:
    - sku_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # M365 SKU ID

naming:
  pattern: "{initials}.{lastname}@{domain}"
  fallback_patterns:
    - "{initials}.{lastname}{n}@{domain}"
    - "{firstname}.{lastname}@{domain}"
```

### 3. Applicatie starten

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## Docker

```bash
# Productie starten
docker-compose up -d

# Development (hot-reload, demo-modus)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Zorg dat `.env` aanwezig is en `config/config.yaml` is geconfigureerd voordat u Docker start.

---

## AFAS GetConnector instellen

AFAS-link verwacht een GetConnector in AFAS Profit met medewerkergegevens. De standaard connector-ID is `HrPersonContact`, maar u kunt een eigen connector maken.

Minimaal vereiste velden:

| AFAS-veld | Beschrijving |
|---|---|
| `EmId` | Medewerker-ID (verplicht) |
| `VoornaamVolledig` | Voornaam |
| `Initialen` | Initialen |
| `Nm` | Achternaam |
| `FunctionDescription` | Functieomschrijving |
| `DepartmentDescription` | Afdelingsomschrijving |
| `StartDate` | Datum in dienst |
| `EndDate` | Datum uit dienst |
| `Mutatiedatum` | Laatste wijzigingsdatum (voor incrementele sync) |

Zie `config/mappings.example.yaml` voor de volledige veldmapping-configuratie.

---

## Entra ID app-registratie

Maak een app-registratie aan in de [Azure Portal](https://portal.azure.com) met de volgende API-permissies (applicatiepermissies, niet gedelegeerd):

- `User.ReadWrite.All`
- `Group.ReadWrite.All`
- `Directory.ReadWrite.All`

Genereer een client secret en sla de waarden op in `.env`.

---

## Configuratie: attributen en groepen

### Attributenmapping (`config/mappings.yaml`)

```yaml
attribute_mapping:
  - afas_field: "EmId"
    internal_field: "afas_employee_id"
  - afas_field: "VoornaamVolledig"
    internal_field: "first_name"
  - afas_field: "Nm"
    internal_field: "last_name"
  - afas_field: "FunctionDescription"
    internal_field: "function"
  - afas_field: "DepartmentDescription"
    internal_field: "department"
  - afas_field: "StartDate"
    internal_field: "start_date"
    transform: date_iso
  - afas_field: "EndDate"
    internal_field: "end_date"
    transform: date_iso
```

### Groepstoewijzingen

```yaml
group_mappings:
  # Alle medewerkers in één Entra-groep
  - afas_field: "*"
    afas_value: "*"
    target: entra_id
    group_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

  # ICT-afdeling in specifieke groep
  - afas_field: "department"
    afas_value: "ICT"
    target: entra_id
    group_id: "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

  # Managers in AD-groep
  - afas_field: "function"
    afas_value: "Manager"
    target: active_directory
    group_dn: "CN=Managers,OU=Groups,DC=bedrijf,DC=local"
```

### OU-toewijzingen (Active Directory)

```yaml
ou_mappings:
  - afas_field: "department"
    afas_value: "ICT"
    ou: "OU=ICT,OU=Medewerkers,DC=bedrijf,DC=local"
  - default: "OU=Medewerkers,DC=bedrijf,DC=local"
```

---

## Tests uitvoeren

```bash
pytest tests/ -v
```

---

## Projectstructuur

```
AFAS-link/
├── src/
│   ├── main.py                  # FastAPI applicatie en lifespan
│   ├── config.py                # Configuratie laden uit YAML + .env
│   ├── database.py              # SQLAlchemy setup
│   ├── scheduler.py             # APScheduler voor geplande syncs
│   ├── models/                  # SQLAlchemy ORM-modellen
│   ├── connectors/
│   │   ├── afas.py              # AFAS REST API connector
│   │   ├── entra_id.py          # Microsoft Graph API connector
│   │   ├── active_directory.py  # LDAP3 AD connector
│   │   └── mock_*.py            # Mock-connectors voor demo/tests
│   ├── engines/
│   │   ├── sync_engine.py       # Provisioning-orkestrator
│   │   ├── naming_engine.py     # E-mailadres- en gebruikersnaamgeneratie
│   │   └── mapping_engine.py    # Veld- en groepsmapping
│   ├── api/                     # FastAPI routers
│   └── templates/               # Jinja2 HTML-templates
├── config/
│   ├── config.example.yaml      # Voorbeeldconfiguratie
│   └── mappings.example.yaml    # Voorbeeldmapping
├── scripts/
│   └── seed_demo.py             # Demo-data seeder
├── tests/                       # Unit tests
├── static/                      # CSS en JavaScript
├── .env.example                 # Voorbeeld omgevingsvariabelen
├── Dockerfile
└── docker-compose.yml
```

---

## Licentie

MIT
