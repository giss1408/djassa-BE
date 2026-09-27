pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        choice(
            name: 'DEPLOY_TARGET',
            choices: ['none', 'vps-test', 'kubernetes'],
            description: 'Deployment target. Keep none for validation-only builds.'
        )
        booleanParam(
            name: 'PUBLISH_IMAGE',
            defaultValue: false,
            description: 'Push the image to the configured registry. Main branch builds may enable this.'
        )
    }

    environment {
        IMAGE_NAME = 'djassa/api'
        REGISTRY = credentials('djassa-container-registry-url')
        IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_COMMIT ?: 'working'}"
        DOCKER_BUILDKIT = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.SHORT_COMMIT = sh(
                        script: 'git rev-parse --short=12 HEAD',
                        returnStdout: true
                    ).trim()
                    env.FULL_IMAGE = "${env.REGISTRY}/${env.IMAGE_NAME}:${env.BUILD_NUMBER}-${env.SHORT_COMMIT}"
                }
            }
        }

        stage('Validate source') {
            steps {
                sh '''
                    set -eu
                    python3 -m py_compile \
                      backend-api/app/main.py \
                      backend-api/app/core/security.py \
                      backend-api/app/api/*.py \
                      backend-api/app/schemas/*.py
                    bash -n backend-api/deploy-vps-test.sh backend-api/deploy-poc.sh
                    git diff --check
                '''
            }
        }

        stage('Build image') {
            steps {
                sh 'docker build --pull -t "$FULL_IMAGE" backend-api'
            }
        }

        stage('Test') {
            steps {
                sh '''
                    set -eu
                    docker run --rm \
                      -e DJASSA_SECRET_KEY=test-only-jwt-secret \
                      -e MOBILE_MONEY_SECRETS=dev-secret \
                      -e PYTHONPATH=/workspace \
                      -v "$WORKSPACE/backend-api:/workspace:ro" \
                      -w /workspace \
                      "$FULL_IMAGE" \
                      pytest -q -p no:cacheprovider
                '''
            }
        }

        stage('Migration test') {
            steps {
                sh '''
                    set -eu
                    docker run --rm \
                      -e DJASSA_SECRET_KEY=test-only-jwt-secret \
                      -e MOBILE_MONEY_SECRETS=dev-secret \
                      -e PYTHONPATH=/workspace \
                      -v "$WORKSPACE/backend-api:/workspace:ro" \
                      -w /workspace \
                      "$FULL_IMAGE" \
                      sh -lc 'rm -f /tmp/djassa-migration.db; DATABASE_URL=sqlite+aiosqlite:////tmp/djassa-migration.db alembic -c alembic.ini upgrade head; DATABASE_URL=sqlite+aiosqlite:////tmp/djassa-migration.db alembic -c alembic.ini current'
                '''
            }
        }

        stage('SBOM') {
            steps {
                sh '''
                    set -eu
                    command -v syft >/dev/null 2>&1 || { echo "syft is required on the Jenkins agent" >&2; exit 1; }
                    mkdir -p artifacts
                    syft "$FULL_IMAGE" -o cyclonedx-json > artifacts/sbom.cdx.json
                '''
            }
        }

        stage('Vulnerability scan') {
            steps {
                sh '''
                    set -eu
                    command -v trivy >/dev/null 2>&1 || { echo "trivy is required on the Jenkins agent" >&2; exit 1; }
                    trivy image --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed "$FULL_IMAGE"
                '''
            }
        }

        stage('Publish image') {
            when {
                allOf {
                    expression { params.PUBLISH_IMAGE }
                    anyOf {
                        branch 'main'
                        branch 'master'
                    }
                }
            }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'djassa-container-registry',
                    usernameVariable: 'REGISTRY_USERNAME',
                    passwordVariable: 'REGISTRY_PASSWORD'
                )]) {
                    sh '''
                        set -eu
                        echo "$REGISTRY_PASSWORD" | docker login "$REGISTRY" --username "$REGISTRY_USERNAME" --password-stdin
                        docker push "$FULL_IMAGE"
                        docker tag "$FULL_IMAGE" "$REGISTRY/$IMAGE_NAME:main"
                        docker push "$REGISTRY/$IMAGE_NAME:main"
                        docker logout "$REGISTRY"
                    '''
                }
            }
        }

        stage('Deploy VPS test') {
            when {
                allOf {
                    expression { params.DEPLOY_TARGET == 'vps-test' }
                    branch 'integration'
                }
            }
            steps {
                sshagent(credentials: ['djassa-vps-ssh']) {
                    withCredentials([
                        string(credentialsId: 'djassa-vps-host', variable: 'VPS_HOST'),
                        string(credentialsId: 'djassa-vps-user', variable: 'VPS_USER')
                    ]) {
                        sh '''
                            set -eu
                            ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$VPS_USER@$VPS_HOST" \
                              'cd /opt/djassa/djassa/backend-api && git fetch --prune && git checkout integration && git pull --ff-only && ./deploy-vps-test.sh'
                        '''
                    }
                }
            }
        }

        stage('Deploy Kubernetes') {
            when {
                allOf {
                    expression { params.DEPLOY_TARGET == 'kubernetes' && params.PUBLISH_IMAGE }
                    anyOf {
                        branch 'main'
                        branch 'master'
                    }
                }
            }
            steps {
                withCredentials([file(credentialsId: 'djassa-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        set -eu
                        command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required on the Jenkins agent" >&2; exit 1; }
                        kubectl apply -f Architecture/k8s/namespace.yaml
                        kubectl apply -f Architecture/k8s/rbac.yaml
                        kubectl apply -f Architecture/k8s/external-secret-store.yaml
                        kubectl apply -f Architecture/k8s/external-secret-djassa.yaml
                        kubectl apply -f Architecture/k8s/service-clusterip.yaml
                        kubectl apply -f Architecture/k8s/deployment-secure.yaml
                        kubectl set image deployment/djassa-api api="$FULL_IMAGE"
                        kubectl apply -f Architecture/k8s/ingress-tls.yaml
                        kubectl apply -f Architecture/k8s/networkpolicy.yaml
                        kubectl rollout status deployment/djassa-api --timeout=180s
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'artifacts/**', allowEmptyArchive: true, fingerprint: true
            sh(script: 'docker image rm "$FULL_IMAGE" >/dev/null 2>&1 || true', returnStatus: true)
        }
        success {
            echo 'Djassa CI/CD pipeline completed successfully.'
        }
        failure {
            echo 'Djassa CI/CD pipeline failed. Review the stage logs and archived SBOM.'
        }
    }
}
