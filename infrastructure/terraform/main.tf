terraform {
  required_version = ">= 1.8"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.32"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.14"
    }
  }

  # Backend remoto configurable por ambiente (S3, GCS, Terraform Cloud)
  # backend "s3" {
  #   bucket = "platform-tfstate"
  #   key    = "platform/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

# Placeholder: cluster Kubernetes se aprovisiona según provider
# (DigitalOcean, GKE, EKS, Hetzner Cloud). Los módulos específicos
# viven en archivos separados una vez que se decide el proveedor.

provider "kubernetes" {
  config_path = var.kubeconfig_path
}

provider "helm" {
  kubernetes {
    config_path = var.kubeconfig_path
  }
}

variable "kubeconfig_path" {
  type        = string
  default     = "~/.kube/config"
  description = "Ruta al kubeconfig del cluster destino"
}

variable "environment" {
  type        = string
  description = "Ambiente destino (staging | production)"
}
