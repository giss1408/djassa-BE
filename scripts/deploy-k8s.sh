#!/usr/bin/env bash
set -euo pipefail

# Deploy djassa Kubernetes manifests. Assumes kubectl is configured.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K8S_DIR="${ROOT_DIR}/Architecture/k8s"

echo "Applying Kubernetes manifests from ${K8S_DIR}"
kubectl apply -f ${K8S_DIR}/cert-manager-clusterissuer.yaml
kubectl apply -f ${K8S_DIR}/namespace.yaml
kubectl apply -f ${K8S_DIR}/rbac.yaml
kubectl apply -f ${K8S_DIR}/external-secret-store.yaml
kubectl apply -f ${K8S_DIR}/external-secret-djassa.yaml
kubectl apply -f ${K8S_DIR}/service-clusterip.yaml
kubectl apply -f ${K8S_DIR}/deployment-secure.yaml
kubectl apply -f ${K8S_DIR}/ingress-tls.yaml
kubectl apply -f ${K8S_DIR}/networkpolicy.yaml

echo "Manifests applied. Verify with: kubectl get pods, svc, ingress -n <namespace>"
