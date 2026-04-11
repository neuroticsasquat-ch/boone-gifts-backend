variable "cors_origins" {
  description = "List of allowed CORS origins"
  type        = list(string)
  default     = ["https://boone.gift", "https://boone.christmas"]
}
