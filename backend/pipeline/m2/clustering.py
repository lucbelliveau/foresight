from collections import defaultdict
from datetime import datetime
import configparser
import json
import sys


from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from bertopic.vectorizers import ClassTfidfTransformer
from bertopic.representation import KeyBERTInspired
from bertopic import BERTopic

from sentence_transformers import SentenceTransformer, util


def load_config(file_name):
    config = configparser.ConfigParser()
    config.read_file(open(file_name))
    return config


def stat_runner(func):
    
    def wrap(*args, **kwargs): 
        start_time = datetime.now()
        total, result = func(*args, **kwargs) 
        end_time = datetime.now()
        seconds = (end_time - start_time).total_seconds()
        if total > 0:
            print(f"{func.__name__} --- {seconds} secs --- {total} docs --- {seconds/total:0.2f} secs per doc.", flush=True)
        return result 
    return wrap 


@stat_runner
def load_batch(file_name, embedding_model):
    with open(file_name, 'rt') as in_file:
        documents = [json.loads(line.strip()) for line in in_file.readlines()]
        texts = [f"{d['title']}\n\n{d['content']}" for d in documents]
        embeddings = embedding_model.encode(texts, show_progress_bar=True)
        total = len(documents)
        return total, [embeddings, texts, documents]


def load_batches(in_path, date_list, start_date, end_date, embedding_model):
    batches = []
    for pub_date in date_list:
        if start_date and (start_date > pub_date or pub_date > end_date):
            continue
        in_file_name = f"{in_path}/processed-{pub_date}-news-articles.jsonl"
        embeddings_texts_documents = load_batch(in_file_name, embedding_model)
        batches.append(embeddings_texts_documents)
    return batches    
   

def create_tools(embedding_model, seed_phrases):
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine', random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=15, metric='euclidean', cluster_selection_method='eom', prediction_data=True)
    vectorizer_model = CountVectorizer(stop_words="english", ngram_range=(1, 3), min_df=3)
    ctfidf_model = ClassTfidfTransformer(seed_words=seed_phrases, seed_multiplier=2, bm25_weighting=True, reduce_frequent_words=True)
    # representation_model = MaximalMarginalRelevance(diversity=.5)
    representation_model = KeyBERTInspired()

    return BERTopic(
        embedding_model=embedding_model,            # Step 1 - Extract embeddings
        umap_model=umap_model,                      # Step 2 - Reduce dimensionality
        hdbscan_model=hdbscan_model,                # Step 3 - Cluster reduced embeddings
        vectorizer_model=vectorizer_model,          # Step 4 - Tokenize topics
        ctfidf_model=ctfidf_model,                  # Step 5 - Extract topic words
        representation_model=representation_model,  # Step 6 - (Optional) Fine-tune topic representations
        top_n_words=15,
        verbose=True
    )
    

@stat_runner
def cluster_batch(batch, embedding_model, seed_phrases):
    topic_model = create_tools(embedding_model, seed_phrases)
    embeddings, texts, _ = batch
    topic_model.fit_transform(texts, embeddings)
    return len(texts), topic_model


def cluster_batches(batches, embedding_model, seed_phrases, print_topics=False):
    topic_model = None
    for batch in batches:
        if not topic_model:
            topic_model = cluster_batch(batch, embedding_model, seed_phrases)
        else:
            batch_model = cluster_batch(batch, embedding_model, seed_phrases)
            topic_model = BERTopic.merge_models([topic_model, batch_model], min_similarity=0.9)
        if print_topics:
            print(topic_model.get_topic_info(), flush=True)
    return topic_model


@stat_runner
def predict_batch(topic_model, batch, topic_dict):
    embeddings, texts, documents = batch
    topics, probs = topic_model.transform(texts, embeddings)
    for topic, prob, doc_id in zip(topics, probs, [d['id'] for d in documents]):
        topic_id = int(topic)
        if topic_id not in topic_dict:
            topic_dict[topic_id] = {'docs': []}
        topic_dict[topic_id]['docs'].append([doc_id, prob])
    return len(texts), topic_dict
    

def predict_batches(topic_model, batches):
    topic_dict = dict()
    for batch in batches:
        topic_dict = predict_batch(topic_model, batch, topic_dict)
    return topic_dict


def get_topic_info(topic_model, batches, topic_dict):
    all_texts = [t for _, texts, _ in batches for t in texts]
    document_info = topic_model.get_document_info(all_texts)
    headers, rows = document_info.columns.tolist(), document_info.values.tolist()
    for row in rows:
        row_dict = {header: value for header, value in zip(headers, row)}
        topic_id = int(row_dict['Topic'])
        if topic_id in topic_dict:
            topic_dict[topic_id].update({'name': row_dict['Name'], 'keywords': row_dict['Representation']})
    return topic_dict


def increase_count(count, character):
    count += 1
    print(character, end="", flush=True)
    return count


def compute_similarity(documents, similarity_threshold, content_similarity_ratio):
    count = 0
    similarity_dict = defaultdict(list)
    for f, f_embeddings in enumerate(documents[:-1]):
        for s, s_embeddings in enumerate(documents[f+1:]):
            total_f_length, total_s_length = len(f_embeddings), len(s_embeddings)
            cos_sim = util.cos_sim(f_embeddings, s_embeddings)

            paragraph_pairs_dict = dict()
            for i in range(len(f_embeddings)-1):
                for j in range(len(s_embeddings)-1):
                    paragraph_pairs_dict[cos_sim[i][j]] = [i, j]

            total_score, f_ids, s_ids = 0.0, [], []
            for k in sorted(paragraph_pairs_dict.keys(), reverse=True):
                if float(k) < similarity_threshold:
                    break
                i, j = paragraph_pairs_dict[k]
                if i in f_ids or j in s_ids:
                    continue
                total_score += float(k)
                f_ids.append(i)
                s_ids.append(j)
                if len(f_ids) == total_f_length or len(s_ids) ==  total_s_length:
                    break
            
            min_length = min(total_f_length, total_s_length)
            len_f_ids = len(f_ids)
            if (len_f_ids == 1 and min_length == 1) or \
                (2 <= min_length <=3 and len_f_ids >= content_similarity_ratio * min_length) or \
                (len_f_ids >= 3):
                if total_s_length < total_f_length:
                    key_id, val_id = s+f+1, f
                else:
                    key_id, val_id = f, s+f+1
                similarity_dict[key_id].append([val_id, total_score/min_length])
                count = increase_count(count, '.')

    return similarity_dict


if __name__ == '__main__':
    start_time = datetime.now()

    config = load_config(sys.argv[1])

    model_name = 'sentence-transformers/all-MiniLM-L6-v2'
    embedding_model = SentenceTransformer(model_name)

    seed_phrases = [p for l in eval(config['seed_phrases']['CUSTOM_TOPICS']).values() for p in l]
    print(f"Read {len(seed_phrases)} seed phrases.")

    date_list = [f"{month}-{day:02}" for month in ['2019-12', '2020-01'] for day in range(1, 32)]
    in_path, start_date, end_date = sys.argv[2], sys.argv[3], sys.argv[4]
    
    batches = load_batches(in_path, date_list, start_date, end_date, embedding_model)
    
    topic_model = cluster_batches(batches, embedding_model, seed_phrases, print_topics=True)

    topic_dict = predict_batches(topic_model, batches)
    
    topic_dict = get_topic_info(topic_model, batches, topic_dict)
    for topic_id in sorted(topic_dict.keys()):
        if 'name' in topic_dict[topic_id]:
            print(f"{topic_id} --- [{len(topic_dict[topic_id]['docs'])}] --- {topic_dict[topic_id]['name']} --- {topic_dict[topic_id]['keywords']}")
        else:
            print(f"{topic_id} --- [{len(topic_dict[topic_id]['docs'])}] --- {topic_model.topic_labels_[topic_id]}")

    topic_keywords, topic_ids = [], []
    for topic_id in sorted(topic_dict.keys()):
        if topic_id != -1 and 'name' in topic_dict[topic_id] and not topic_dict[topic_id]['name'].startswith('-1'):
            topic_keywords.append(embedding_model.encode(topic_dict[topic_id]['keywords']))
            topic_ids.append(topic_id)
            
    similarity_dict = compute_similarity(topic_keywords, similarity_threshold=0.80, content_similarity_ratio=0.5)
    for key_id, similarity_list in similarity_dict.items():
        topic_kid = topic_ids[key_id]
        print(f"{topic_kid} --- [{len(topic_dict[topic_kid]['docs'])}] --- {topic_dict[topic_kid]['name']} --- {topic_dict[topic_kid]['keywords']}")
        for val_id, score in similarity_list:
            topic_sid = topic_ids[val_id]
            print(f"\t{score:0.2f} --- {topic_sid} --- [{len(topic_dict[topic_sid]['docs'])}] --- {topic_dict[topic_sid]['name']} --- {topic_dict[topic_sid]['keywords']}")

    end_time = datetime.now()
    seconds = (end_time - start_time).total_seconds()
    print(f"Executed in {seconds} secs.", flush=True)

