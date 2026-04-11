variable "cors_origins" {
  description = "List of allowed CORS origins"
  type        = list(string)
  default     = ["https://app.boone.gift", "https://app.boone.christmas"]
}
