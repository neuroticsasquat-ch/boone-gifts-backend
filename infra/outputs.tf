output "app_url" {
  description = "Default URL of the App Service"
  value       = "https://${azurerm_linux_web_app.this.default_hostname}"
}

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.this.name
}

output "app_name" {
  description = "Name of the App Service"
  value       = azurerm_linux_web_app.this.name
}

output "application_insights_name" {
  description = "Name of the Application Insights instance"
  value       = azurerm_application_insights.this.name
}
