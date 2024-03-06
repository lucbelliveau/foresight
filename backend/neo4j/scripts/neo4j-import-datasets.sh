#!/bin/bash

set -e

source deployment/neo4j/.env

echo 'Import Disease Ontology ...'
echo 'Copying scripts and data ...'
sudo cp neo4j/cql/import-disease-ontology.cql deployment/neo4j/import/.
sudo cp datasets/processed-disease-ontology.jsonl deployment/neo4j/import/.
echo 'Executing queries ...'
docker exec -u ${NEO4J_USERNAME} --interactive --tty  neo4j cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} --file /import/import-disease-ontology.cql
echo 'Disease Ontology imported ✅'

echo 'Import Disease Outbreak News ...'
echo 'Copying scripts and data ...'
sudo cp neo4j/cql/import-who-dons.cql deployment/neo4j/import/.
sudo cp datasets/processed-who-dons.jsonl deployment/neo4j/import/.
echo 'Executing queries ...'
docker exec -u ${NEO4J_USERNAME} --interactive --tty  neo4j cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} --file /import/import-who-dons.cql
echo 'Disease Outbreak News Articles imported ✅'

echo 'Import News Articles ...'
echo 'Copying scripts and data ...'
sudo cp neo4j/cql/import-news-articles.cql deployment/neo4j/import/.
sudo cp datasets/*-news-articles.jsonl deployment/neo4j/import/.
sudo cp datasets/*-clusters.jsonl deployment/neo4j/import/.
echo 'Executing queries ...'
docker exec -u ${NEO4J_USERNAME} --interactive --tty  neo4j cypher-shell -u ${NEO4J_USERNAME} -p ${NEO4J_PASSWORD} --file /import/import-news-articles.cql
echo 'Disease Outbreak News Articles imported ✅'
