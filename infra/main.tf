terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-tbc-app-services"
    storage_account_name = "tbcterraformstate"
    container_name       = "tfstate"
    key                  = "boone-gifts-api.tfstate"
  }
}

provider "azurerm" {
  features {}
}

# ---------------------------------------------------------------------------
# Data sources — existing resources
# ---------------------------------------------------------------------------

data "azurerm_service_plan" "this" {
  name                = "asp-tbc-app-services-01"
  resource_group_name = "rg-tbc-app-services"
}

data "azurerm_log_analytics_workspace" "this" {
  name                = "DefaultWorkspace-de448de3-61e7-4067-b981-d1aeb0ce136d-EUS2"
  resource_group_name = "defaultresourcegroup-eus2"
}

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "this" {
  name     = "rg-boone-gifts-api"
  location = "eastus2"
}

# ---------------------------------------------------------------------------
# JWT secret — generated once, stored in state
# ---------------------------------------------------------------------------

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# ---------------------------------------------------------------------------
# Storage — Azure Files share for SQLite persistence
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "this" {
  name                     = "stboonegiftsapi"
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_share" "this" {
  name               = "data"
  storage_account_id = azurerm_storage_account.this.id
  quota              = 1 # GB
}

# ---------------------------------------------------------------------------
# Application Insights
# ---------------------------------------------------------------------------

resource "azurerm_application_insights" "this" {
  name                = "appi-boone-gifts-api"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  workspace_id        = data.azurerm_log_analytics_workspace.this.id
  application_type    = "web"
}

# ---------------------------------------------------------------------------
# App Service — Linux Web App with custom container
# ---------------------------------------------------------------------------

resource "azurerm_linux_web_app" "this" {
  name                = "app-boone-gifts-api"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  service_plan_id     = data.azurerm_service_plan.this.id

  site_config {
    application_stack {
      docker_registry_url = "https://ghcr.io"
      docker_image_name   = "tomboone/boone-gifts-backend:latest"
    }

    health_check_path                 = "/health"
    health_check_eviction_time_in_min = 5
  }

  app_settings = {
    "APP_DATABASE_URL"                       = "sqlite:////data/boone_gifts.db"
    "APP_JWT_SECRET"                         = random_password.jwt_secret.result
    "APP_CORS_ORIGINS"                       = jsonencode(var.cors_origins)
    "WEBSITES_PORT"                          = "8000"
    "APPLICATIONINSIGHTS_CONNECTION_STRING"  = azurerm_application_insights.this.connection_string
  }

  storage_account {
    name         = "data"
    type         = "AzureFiles"
    account_name = azurerm_storage_account.this.name
    share_name   = azurerm_storage_share.this.name
    access_key   = azurerm_storage_account.this.primary_access_key
    mount_path   = "/data"
  }

  logs {
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }
}
