from datetime import datetime
import json
import os
from queue import Queue
from threading import Thread
import sys

from wordcloud import WordCloud
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer

from umap import UMAP
from hdbscan import HDBSCAN
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired, MaximalMarginalRelevance
from bertopic.vectorizers import ClassTfidfTransformer

from transformers import pipeline, AutoTokenizer
from langchain.text_splitter import RecursiveCharacterTextSplitter


TOPIC_LIST = [
    'Outbreaks of known infectious diseases',
    'Emerging infectious diseases or novel pathogens',
    'Hurricanes, earthquakes, floods, wildfires, and their health impacts',
    'Effects on health infrastructure and services during disasters',
    'Air pollution levels and associated health risks',
    'Water contamination issues and their health implications',
    'Chemical spills or industrial accidents affecting public health',
    'Health implications of accidents in industrial settings',
    'Potential biological attacks or bioterrorism threats',
    'Reports on suspicious disease-related incidents', 
    'Reports on suspicious drug-related incidents', 
    'Foodborne illness outbreaks and recalls',
    'Waterborne diseases and contamination alerts',
    'Incidents involving radiation exposure and their health consequences',
    'Extreme weather events and health advisories',
    'Health implications of changing climate patterns',
    'Outbreaks linked to vaccine-preventable diseases',
    'Controversies or developments in vaccination policies',
    'Security breaches or cyberattacks on healthcare systems',
    'Risks to patient data and healthcare services',
    'Evaluations of healthcare system readiness during emergencies',
    'Reports on hospital capacity during crises or emergencies',
    'Drug recalls, counterfeit drugs, and safety concerns',
    'Issues with medical device safety, recalls, and their impact on health',
    'Unusual health patterns',
    'Emerging pathogens',
    'Abnormal environmental indicators',
    'Unforeseen health outcomes',
    'Anomalous disease clusters',
    'Unrecognized health risks',
    'Atypical health incidents'
]


def increase_count(count, character):
    count += 1
    print(character, end="", flush=True)
    return count


def summarize_text_task(worker_id, device, document_list, queue):
    device_id = 'mps' if device == 'mps' else worker_id
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn",  device=device_id)
    
    for document in document_list:
        summary = summarizer(document, max_length=130, min_length=30, do_sample=False)[0]['summary_text']
        print('+', end="", flush=True)
        queue.put(summary)
        

def summarize_text(n_workers, input_documents, device):
    batch_size = len(input_documents) // n_workers

    sub_lists = []
    for i in range(0, n_workers-1):
        sub_lists.append(input_documents[i * batch_size: (i+1) * batch_size])
    sub_lists.append(input_documents[(n_workers - 1) * batch_size:])

    output_queue = Queue()
    workers = []
    for i in range(0, n_workers):
        workers.append(Thread(target=summarize_text_task, args=(i, device, sub_lists[i], output_queue,)))
        
    for i in range(0, n_workers):
        workers[i].start()
    
    for i in range(0, n_workers):
        workers[i].join()
        
    output_documents = []
    while True:
        document = output_queue.get()
        if document is None:
            break
        
        output_documents.append(document)
        if len(output_documents) == len(input_documents):
            break
    return output_documents


def classify_text_task(worker_id, device, document_list, queue):
    device_id = 'mps' if device == 'mps' else worker_id
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli",  device=device_id)
    
    for document in document_list:
        result = classifier(document, TOPIC_LIST, multi_label=True)
        topics = {topic: score for topic, score in zip(result['labels'], result['scores']) if score > 0.9}
        
        if topics:
            print('.', end="", flush=True)
        else:
            print(' ', end="", flush=True)
        queue.put(topics)
        

def classify_text(n_workers, input_documents, device):
    batch_size = len(input_documents) // n_workers

    sub_lists = []
    for i in range(0, n_workers-1):
        sub_lists.append(input_documents[i * batch_size: (i+1) * batch_size])
    sub_lists.append(input_documents[(n_workers - 1) * batch_size:])

    output_queue = Queue()
    workers = []
    for i in range(0, n_workers):
        workers.append(Thread(target=classify_text_task, args=(i, device, sub_lists[i], output_queue,)))
        
    for i in range(0, n_workers):
        workers[i].start()
    
    for i in range(0, n_workers):
        workers[i].join()
        
    output_documents = []
    while True:
        document = output_queue.get()
        if document is None:
            break
        
        output_documents.append(document)
        if len(output_documents) == len(input_documents):
            break
    return output_documents


if __name__ == '__main__':
    path, single_date = sys.argv[1], sys.argv[2]
    device = sys.argv[3] if len(sys.argv) > 3 else None

    doc_dict = dict()
    for file in sorted(os.listdir(path)):
        file_name = os.path.join(path, file)
        if not os.path.isfile(file_name) \
            or not file.startswith('processed-') \
            or not file.endswith('-news-articles.jsonl') \
            or not file.endswith('.jsonl'):
            continue

        if single_date not in file:
            continue
        
        pub_date = file[10:20]
        start_time = datetime.now()

        count = 0
        documents = []
        with open(file_name, 'rt') as in_file:
            for line in in_file.readlines():
                document = json.loads(line.strip())
                documents.append(document)
                count = increase_count(count, '.')
        doc_dict[pub_date] = documents
        print(f"\n[{pub_date}] Read {count} articles.\n")

        # # System prompt describes information given to all conversations
        # LABELING_PROMPT_TEMPLATE = """
        # You are a helpful, respectful and honest assistant for labeling topics.

        # I have a topic that contains the following documents delimited by triple backquotes (```). 
        # ```{documents}```
        
        # The topic is described by the following keywords delimited by triple backquotes (```):
        # ```{keywords}```

        # Create a concise label of this topic, which should not exceed 32 characters.
        # If there are more than one possible labels, return the shortest one and nothing more.
        
        # {format_instructions}
        # """
        
        # llm = Ollama(model="mistral:instruct")
        # output_parser = NumberedListOutputParser()
        # format_instructions = output_parser.get_format_instructions()

        # labeling_prompt = PromptTemplate(
        #     input_variables=["documents", "keywords"], 
        #     partial_variables={"format_instructions": format_instructions}, 
        #     template=LABELING_PROMPT_TEMPLATE)
        # labeling_llm_chain = LLMChain(llm=llm, prompt=labeling_prompt)

        # SUMMARY_PROMPT_TEMPLATE = """Write a concise summary for all following documents delimited by triple backquotes (```).
        # ```{documents}```

        # {format_instructions}"""
        # summary_prompt = PromptTemplate(
        #     input_variables=["documents"], 
        #     partial_variables={"format_instructions": format_instructions},
        #     template=SUMMARY_PROMPT_TEMPLATE)
        # summary_llm_chain = LLMChain(llm=llm, prompt=summary_prompt)

        # Step 1 - Extract embeddings
        device_id = 'mps' if device == 'mps' else 0
        # sentence_transformer = SentenceTransformer('sentence-transformers/all-mpnet-base-v2', device=device_id)
        embedding_model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2', device=device_id)

        # Step 2 - Reduce dimensionality
        umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine')

        # Step 3 - Cluster reduced embeddings
        hdbscan_model = HDBSCAN(min_cluster_size=15, metric='euclidean', cluster_selection_method='eom', prediction_data=True)

        # Step 4 - Tokenize topics
        vectorizer_model = CountVectorizer(stop_words="english")

        # Step 5 - Create topic representation
        ctfidf_model = ClassTfidfTransformer(reduce_frequent_words=True)

        # Step 6 - (Optional) Fine-tune topic representations with 
        # a `bertopic.representation` model
        representation_model = KeyBERTInspired()

        # All steps together
        topic_model = BERTopic(
            embedding_model=embedding_model,            # Step 1 - Extract embeddings
            umap_model=umap_model,                      # Step 2 - Reduce dimensionality
            hdbscan_model=hdbscan_model,                # Step 3 - Cluster reduced embeddings
            vectorizer_model=vectorizer_model,          # Step 4 - Tokenize topics
            ctfidf_model=ctfidf_model,                  # Step 5 - Extract topic words
            representation_model=representation_model,  # Step 6 - (Optional) Fine-tune topic representations
            calculate_probabilities=True,
        )
        
        classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli", device=device_id)
       
        print('Compute embeddings ...')
        texts = ['\n\n'.join([document[prop] for prop in ['title', 'content']]) for document in doc_dict[pub_date]]
        if device == 'cuda':
            pool = embedding_model.start_multi_process_pool()
            embeddings = embedding_model.encode_multi_process(texts, pool)
        else:
            embeddings = embedding_model.encode(texts, show_progress_bar=True)
        
        print('Start fit_transform ...')
        topics, probs = topic_model.fit_transform(texts, embeddings)
        print(topic_model.get_topic_info())
        
        # Reduce outliers
        new_topics = topic_model.reduce_outliers(texts, topics, probabilities=probs, strategy="probabilities")
        new_topics = topic_model.reduce_outliers(texts, topics, strategy="embeddings", embeddings=embeddings)
        topic_model.update_topics(texts, topics=new_topics)
        print(topic_model.get_topic_info())
        
        # print(topic_model.topic_aspects_)
        topic_labels = topic_model.generate_topic_labels(nr_words=5, topic_prefix=False, word_length=10, separator=", ")
        topic_model.set_topic_labels(topic_labels)
        print(topic_model.get_topic_info())
        
        topic_set = set(topics)
        label_dict = dict()
        for topic in topic_set:
            if topic != -1:
                label_dict[topic] = topic_model.topic_labels_[topic]
                print(f"[{topic}] {label_dict[topic]}")
               
        input_documents = [topic_model.representative_docs_[topic][0] for topic in topic_set if topic != -1]

        n_workers = 4
        classified_topics_list = classify_text(n_workers, input_documents, device)
        for topic, classified_topics in enumerate(classified_topics_list):
            print(f"[{topic}] --- {classified_topics}")
        
        summaries = summarize_text(n_workers, input_documents, device)
        for topic, summary in enumerate(summaries):
            print(f"[{topic}] --- {summary}")

        # label_dict, summary_dict = dict(), dict()
        # for i in range(-1, len(topic_model.get_topic_info())-1):
        #     if i == -1:
        #         label_dict[i] = 'Outlier Topic'
        #         summary_dict[i] = ''
                
        #     else:
        #         keywords = topic_model.topic_labels_[i].split('_')[1:]
        #         representative_docs = topic_model.representative_docs_[i]
        #         # output = labeling_llm_chain.invoke({'documents': representative_docs[0], 'keywords': keywords})['text']
        #         label_dict[i] = output_parser.parse(output)[0]
                
        #         output = summary_llm_chain.invoke({'documents': representative_docs[0]})['text']
        #         summary_dict[i] = sorted(output_parser.parse(output), reverse=True)[0]
                
        #         print(f"[{i}] {label_dict[i]} --- {summary_dict[i]}")

        # topic_model.set_topic_labels(label_dict)
        # print(topic_model.get_topic_info())
        
        grouped_topics = {
            topic: { 
                'id_list': [], 'label': label_dict[topic] if topic != -1 else "Outliers", 
                'summary': summaries[topic] if topic != -1 else '', 
                'threats': classified_topics_list[topic] if topic != -1 else ''
            } 
            for topic in topic_set
        }
        for index, topic in enumerate(topics):
            grouped_topics[topic]['id_list'].append(doc_dict[pub_date][index]['id'])
            
        count = 0
        for topic in topic_set:
            count += len(grouped_topics[topic]['id_list'])
        print(count, len(doc_dict[pub_date]))
        assert count == len(doc_dict[pub_date])
        
        for topic in topic_set:
            if topic != -1:
                text = {word: value for word, value in topic_model.get_topic(topic)}
                wc = WordCloud(background_color="white", max_words=1000)
                wc.generate_from_frequencies(text)
                plt.imshow(wc, interpolation="bilinear")
                plt.axis("off")
                plt.savefig('viz/' + pub_date + '-' + str(topic) + '.png')
        
        cluster_file_name = 'datasets/' + pub_date + '-clusters.jsonl'
        with open(cluster_file_name, 'wt') as out_file:
            out_file.write(f"{json.dumps(grouped_topics)}\n")
        print(f"\nWritten {cluster_file_name}.\n")
        
        viz_hie_arch = topic_model.visualize_hierarchy(custom_labels=True)
        viz_hie_arch.write_html("viz/" + pub_date + '-hie.html')

        # Reduce dimensionality of embeddings, this step is optional but much faster to perform iteratively:
        reduced_embeddings = UMAP(n_neighbors=10, n_components=2, min_dist=0.0, metric='cosine').fit_transform(embeddings)
        viz_docs = topic_model.visualize_documents(texts, reduced_embeddings=reduced_embeddings, width=2048, height=1536, custom_labels=True)
        viz_docs.write_html("viz/" + pub_date + '-cls.html')
        
        if device == 'cuda':
            embedding_model.stop_multi_process_pool(pool)
        
        end_time = datetime.now()
        seconds = (end_time - start_time).total_seconds()
        print(f"\nTotal {len(doc_dict[pub_date])} documents in {seconds} seconds: {seconds*1000/(len(doc_dict[pub_date])):0.3f} seconds per 1K documents.", flush=True)

