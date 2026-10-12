#!/bin/bash
set -e

# Pull all remaining SWE-bench Verified Django Docker images
IMAGES=(
    "swebench/sweb.eval.x86_64.django_1776_django-12276:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-11880:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-11885:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-11951:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-11964:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-11999:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12039:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12050:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12143:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12155:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12262:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12304:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12308:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12406:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12708:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12713:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-12774:latest"
    "swebench/sweb.eval.x86_64.django_1776_django-9296:latest"
)

echo "Starting sequential pull of remaining SWE-bench Django images..."
for img in "${IMAGES[@]}"; do
    if docker image inspect "$img" > /dev/null 2>&1; then
        echo "Image $img already exists locally. Skipping."
    else
        echo "Pulling $img..."
        docker pull "$img"
    fi
done
echo "All Django images successfully cached!"
