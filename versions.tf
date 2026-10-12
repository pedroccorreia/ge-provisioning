terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    googleworkspace = {
      source  = "hashicorp/googleworkspace"
      version = ">= 0.7.0"
    }
    external = {
      source  = "hashicorp/external"
      version = ">= 2.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}
