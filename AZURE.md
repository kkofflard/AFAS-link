# AFAS-link — Azure Deployment Handleiding

Deze handleiding beschrijft hoe u AFAS-link deployt op **Azure Container Apps** met **Azure Database for PostgreSQL** en **Azure Key Vault** voor secrets.

---

## Architectuur

```
GitHub Actions
  │  push naar main → docker build → push naar ACR
  │
  └─► Azure Container Apps (1 replica, always-on)
        │  poort 8000, externe HTTPS-ingress
        │  leest secrets via Managed Identity uit Key Vault
        │
        ├─► Azure Database for PostgreSQL (Flexible Server, B1ms)
        │
        └─► Microsoft Entra ID (Graph API via MSAL)
```

---

## Geschatte kosten

| Resource | Tier | ~Kosten/maand |
|---|---|---|
| Container Apps | Consumption, 0.5 vCPU / 1 GB | €5–10 |
| PostgreSQL Flexible Server | Burstable B1ms | €15–20 |
| Container Registry | Basic | €5 |
| Key Vault | Standard | <€1 |
| Log Analytics | Pay-as-you-go | €1–3 |
| **Totaal** | | **~€26–39/maand** |

---

## Vereisten

- [Azure CLI](https://learn.microsoft.com/nl-nl/cli/azure/install-azure-cli) geïnstalleerd en ingelogd (`az login`)
- Een Azure-abonnement
- Een bestaande **Entra ID app-registratie** met:
  - `User.ReadWrite.All`
  - `Group.ReadWrite.All`
  - `Directory.ReadWrite.All`
  - Een client secret
- AFAS REST API-token

---

## Stap 1 — Resource Group aanmaken

```bash
az group create \
  --name afaslink-prod-rg \
  --location westeurope
```

---

## Stap 2 — Parameterbestand aanmaken

Kopieer het voorbeeldbestand en vul uw waarden in:

```bash
cp infra/parameters.example.json infra/parameters.json
```

Bewerk `infra/parameters.json`:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "location":            { "value": "westeurope" },
    "environmentName":     { "value": "prod" },
    "appName":             { "value": "afaslink" },
    "postgresAdminUser":   { "value": "afaslink_admin" },
    "postgresAdminPassword": { "value": "SterkWachtwoord123!" },
    "afasToken":           { "value": "uw-afas-token-data-hier" },
    "entraTenantId":       { "value": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
    "entraClientId":       { "value": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
    "entraClientSecret":   { "value": "uw-client-secret-hier" },
    "emailDomain":         { "value": "uwbedrijf.nl" }
  }
}
```

> **Let op:** Voeg `infra/parameters.json` toe aan `.gitignore` — dit bestand bevat gevoelige gegevens!

---

## Stap 3 — Infrastructure deployen

```bash
az deployment group create \
  --resource-group afaslink-prod-rg \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json
```

Dit duurt ~5–10 minuten. De output bevat de URL van de applicatie:

```
"outputs": {
  "containerAppUrl": { "value": "https://afaslink-prod-app.<regio>.azurecontainerapps.io" }
}
```

---

## Stap 4 — Config YAML uploaden

De applicatie heeft een `config.yaml` nodig. Upload deze naar de Container App als een volume, of stel de inhoud in als environment variables.

**Optie A: Config inbouwen in de Docker image**

Maak een `config/config.yaml` aan (kopieer van `config/config.example.yaml`) en pas aan. Deze wordt automatisch meegebakken in de Docker image bij de volgende deployment.

**Optie B: Azure File Share** (voor productie)

```bash
# Storage account aanmaken
az storage account create \
  --name afaslinkprodconfig \
  --resource-group afaslink-prod-rg \
  --sku Standard_LRS

# File share aanmaken
az storage share create \
  --name afaslink-config \
  --account-name afaslinkprodconfig

# Config uploaden
az storage file upload \
  --account-name afaslinkprodconfig \
  --share-name afaslink-config \
  --source config/config.yaml \
  --path config.yaml
```

---

## Stap 5 — Eerste Docker image pushen

Na het deployen van de infrastructure is de Container App leeg. Push handmatig de eerste image:

```bash
# ACR naam ophalen
ACR_NAME=$(az deployment group show \
  --resource-group afaslink-prod-rg \
  --name main \
  --query "properties.outputs.acrLoginServer.value" \
  --output tsv)

# Inloggen op ACR
az acr login --name ${ACR_NAME%%.*}

# Image bouwen en pushen
docker build -t $ACR_NAME/afaslink:latest .
docker push $ACR_NAME/afaslink:latest

# Container App updaten
az containerapp update \
  --name afaslink-prod-app \
  --resource-group afaslink-prod-rg \
  --image $ACR_NAME/afaslink:latest
```

---

## Stap 6 — GitHub Actions CI/CD instellen

Voor automatische deployments bij elke push naar `main`:

### 6.1 Azure Service Principal aanmaken

```bash
az ad sp create-for-rbac \
  --name afaslink-github-actions \
  --role contributor \
  --scopes /subscriptions/<uw-subscription-id>/resourceGroups/afaslink-prod-rg \
  --sdk-auth
```

Kopieer de JSON-output.

### 6.2 GitHub Secrets instellen

Ga naar uw GitHub repository → **Settings → Secrets and variables → Actions** en voeg toe:

| Secret naam | Waarde |
|---|---|
| `AZURE_CREDENTIALS` | De volledige JSON-output van de vorige stap |

### 6.3 Workflow aanpassen

Bewerk `.github/workflows/azure-deploy.yml` en pas de omgevingsvariabelen aan:

```yaml
env:
  AZURE_RESOURCE_GROUP: afaslink-prod-rg
  CONTAINER_APP_NAME: afaslink-prod-app
  ACR_NAME: afaslinkprodacr         # Zonder .azurecr.io
```

Vanaf nu deployt elke push naar `main` automatisch naar Azure.

---

## Stap 7 — Verificatie

```bash
# URL ophalen
APP_URL=$(az containerapp show \
  --name afaslink-prod-app \
  --resource-group afaslink-prod-rg \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

# Health check
curl https://$APP_URL/api/health

# Dashboard openen
echo "Dashboard: https://$APP_URL"
```

Verwachte output van `/api/health`:

```json
{"status": "ok", "database": "verbonden", "timestamp": "2024-..."}
```

---

## Secrets beheren na deployment

### Extra AFAS-omgeving toevoegen

```bash
az keyvault secret set \
  --vault-name afaslink-prod-kv \
  --name afas-token-env2 \
  --value "uw-tweede-token-data"
```

Voeg daarna het secret toe aan de Container App via de Azure Portal of CLI.

### Client secret vernieuwen

```bash
az keyvault secret set \
  --vault-name afaslink-prod-kv \
  --name entra-client-secret \
  --value "nieuw-client-secret"
```

De Container App pikt de nieuwe waarde automatisch op bij de volgende herstart.

---

## Logboeken bekijken

```bash
# Live logs streamen
az containerapp logs show \
  --name afaslink-prod-app \
  --resource-group afaslink-prod-rg \
  --follow

# Of via Log Analytics (Azure Portal → Log Analytics Workspace → Logs)
# Query voorbeeld:
# ContainerAppConsoleLogs_CL
# | where ContainerName_s == "afaslink"
# | order by TimeGenerated desc
# | take 100
```

---

## Probleemoplossing

### Container start niet op

```bash
az containerapp revision list \
  --name afaslink-prod-app \
  --resource-group afaslink-prod-rg \
  --output table
```

### Database-verbinding mislukt

Controleer of de firewall-regel `AllowAzureServices` aanwezig is op de PostgreSQL-server, en of `DATABASE_URL` in Key Vault het juiste formaat heeft:

```
postgresql://gebruiker:wachtwoord@server.postgres.database.azure.com/afaslink?sslmode=require
```

### Key Vault-toegang geweigerd

Controleer of de Managed Identity de rol `Key Vault Secrets User` heeft op de Key Vault.

---

## Resources verwijderen

```bash
az group delete --name afaslink-prod-rg --yes --no-wait
```

> **Let op:** Dit verwijdert alle resources inclusief de database. Maak eerst een backup als er productiedata aanwezig is.
