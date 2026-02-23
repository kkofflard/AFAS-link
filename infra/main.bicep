// ============================================================
// AFAS-link Azure Infrastructure
// Deploy met: az deployment group create \
//   --resource-group <rg-naam> \
//   --template-file infra/main.bicep \
//   --parameters @infra/parameters.json
// ============================================================

@description('Locatie voor alle resources (bijv. westeurope)')
param location string = 'westeurope'

@description('Omgevingsnaam (bijv. prod, staging)')
param environmentName string = 'prod'

@description('Prefix voor resource-namen (bijv. afaslink)')
param appName string = 'afaslink'

@description('PostgreSQL admin-gebruikersnaam')
param postgresAdminUser string = 'afaslink_admin'

@description('PostgreSQL admin-wachtwoord')
@secure()
param postgresAdminPassword string

@description('AFAS token (het data-gedeelte)')
@secure()
param afasToken string

@description('Entra ID tenant ID')
param entraTenantId string

@description('Entra ID client ID (app-registratie)')
param entraClientId string

@description('Entra ID client secret')
@secure()
param entraClientSecret string

@description('E-maildomein voor nieuwe accounts (bijv. bedrijf.nl)')
param emailDomain string

@description('Config YAML als string (inhoud van config.yaml)')
param configYaml string = ''

// ============================================================
// Variabelen
// ============================================================
var resourcePrefix = '${appName}-${environmentName}'
var acrName = replace('${appName}${environmentName}acr', '-', '')
var keyVaultName = '${resourcePrefix}-kv'
var postgresServerName = '${resourcePrefix}-pg'
var containerAppsEnvName = '${resourcePrefix}-env'
var containerAppName = '${resourcePrefix}-app'
var identityName = '${resourcePrefix}-identity'
var logWorkspaceName = '${resourcePrefix}-logs'

// ============================================================
// Log Analytics Workspace (voor Container Apps monitoring)
// ============================================================
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ============================================================
// User-assigned Managed Identity
// ============================================================
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// ============================================================
// Azure Container Registry
// ============================================================
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Geef Managed Identity pull-rechten op ACR
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'acrpull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================
// Azure Key Vault
// ============================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enableSoftDelete: true
  }
}

// Geef Managed Identity lees-rechten op Key Vault
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, 'kvsecretsuser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Secrets opslaan in Key Vault
resource secretAfasToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'afas-token'
  properties: {
    value: afasToken
  }
}

resource secretPostgresUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: {
    value: 'postgresql://${postgresAdminUser}:${postgresAdminPassword}@${postgresServerName}.postgres.database.azure.com/afaslink?sslmode=require'
  }
}

resource secretEntraClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'entra-client-secret'
  properties: {
    value: entraClientSecret
  }
}

// ============================================================
// Azure Database for PostgreSQL Flexible Server
// ============================================================
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: postgresServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgresServer
  name: 'afaslink'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Sta verbindingen toe vanuit Azure-services (Container Apps)
resource postgresFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ============================================================
// Container Apps Environment
// ============================================================
resource containerAppsEnv 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: containerAppsEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ============================================================
// Container App
// ============================================================
resource containerApp 'Microsoft.App/containerApps@2023-11-02-preview' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: secretPostgresUrl.properties.secretUri
          identity: managedIdentity.id
        }
        {
          name: 'afas-token'
          keyVaultUrl: secretAfasToken.properties.secretUri
          identity: managedIdentity.id
        }
        {
          name: 'entra-client-secret'
          keyVaultUrl: secretEntraClientSecret.properties.secretUri
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1   // Altijd 1 replica — APScheduler mag niet op meerdere instances draaien
        maxReplicas: 1
      }
      containers: [
        {
          name: 'afaslink'
          image: '${acr.properties.loginServer}/afaslink:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'AFAS_ENV1_TOKEN'
              secretRef: 'afas-token'
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'ENTRA_CLIENT_ID'
              value: entraClientId
            }
            {
              name: 'ENTRA_CLIENT_SECRET'
              secretRef: 'entra-client-secret'
            }
            {
              name: 'DEMO_MODE'
              value: 'false'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
            {
              name: 'CONFIG_PATH'
              value: '/app/config/config.yaml'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    acrPullRole
    kvSecretsUserRole
    postgresDatabase
  ]
}

// ============================================================
// Outputs
// ============================================================
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = keyVault.name
output postgresServerName string = postgresServer.name
output managedIdentityClientId string = managedIdentity.properties.clientId
