#!/usr/bin/env python3
import os
import readline # So that input can handle Kanji & delete
import openai
from dotenv import load_dotenv
import json
from datetime import datetime
import re
import random
import pinecone
import tiktoken  # for counting tokens

# Configuration
load_dotenv() # Load default environment variables (.env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
assert OPENAI_API_KEY, "OPENAI_API_KEY environment variable is missing from .env"
OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "gpt-3.5-turbo")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.7))
EMBEDDING_MODEL = "text-embedding-ada-002"
TOKEN_BUDGET = 4096 - 500
# print(f"Open AI Key = {OPENAI_API_KEY}")
print(f"Model = {OPENAI_API_MODEL}")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
assert PINECONE_API_KEY, "PINECONE_API_KEY environment variable is missing from .env"
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "")
assert (
    PINECONE_ENVIRONMENT
), "PINECONE_ENVIRONMENT environment variable is missing from .env"

# Initialize Pinecone & OpenAI
pinecone.init(api_key=PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)
openai.api_key = OPENAI_API_KEY

oneline_help = "System Slashes: /bye, /reset, /help, /prompt, /gpt3, /gpt4"
print(oneline_help)

# Reading Manifest files
manifests = {}
files = os.listdir("./prompts")

if not os.path.isdir("output"):
    os.makedirs("output")
if not os.path.isdir("output/GPT"):
    os.makedirs("output/GPT")

# print(files)
for file in files:
    key = file.split('.')[0]
    with open(f"./prompts/{file}", 'r') as f:
        data = json.load(f)
    # print(key, file, data)
    manifests[key] = data

class ChatContext:
    def __init__(self, role: str = "GPT", manifest = None):
        self.role = role
        self.time = datetime.now()
        self.userName = "You"
        self.botName = "GPT"
        self.title = ""
        self.intro = None
        self.temperature = OPENAI_TEMPERATURE
        self.manifest = manifest
        self.prompt = None
        self.index = None
        self.model = OPENAI_API_MODEL
        self.messages = []
        if (manifest):
            self.userName = manifest.get("you") or self.userName
            self.botName = manifest.get("bot") or context.role
            self.model = manifest.get("model") or self.model
            self.title = manifest.get("title")
            self.intro = manifest.get("intro")
            if (manifest.get("temperature")):
                self.temperature = float(manifest.get("temperature"))
            self.prompt = '\n'.join(manifest["prompt"])
            data = manifest.get("data")
            if data:
                # Shuffle 
                for i in range(len(data)):
                    j = random.randrange(0, len(data))
                    temp = data[i]
                    data[i] = data[j]
                    data[j] = temp
                j = 0
                while(re.search("\\{random\\}", self.prompt)):
                    self.prompt = re.sub("\\{random\\}", data[j], self.prompt, 1)
                    j += 1
            table_name = manifest.get("articles")
            if table_name:
                assert table_name in pinecone.list_indexes(), f"No Pinecone table named {table_name}"
                self.index = pinecone.Index(table_name)
            self.messages = [{"role":"system", "content":self.prompt}]

    def num_tokens(self, text: str) -> int:
        """Return the number of tokens in a string."""
        encoding = tiktoken.encoding_for_model(context.model)
        return len(encoding.encode(text))
    
    def fetch_related_articles(
        self,
        token_budget: int = TOKEN_BUDGET
    ) -> str:
        """Return related articles with the question using the embedding vector search."""
        query = ""
        for message in self.messages:
            if (message["role"] == "user"):
                query = message["content"] + "\n" + query
        query_embedding_response = openai.Embedding.create(
            model=EMBEDDING_MODEL,
            input=query,
        )
        query_embedding = query_embedding_response["data"][0]["embedding"]

        results = self.index.query(query_embedding, top_k=100, include_metadata=True)

        articles = ""
        for match in results["matches"]:
            string = match["metadata"]["text"]
            next_article = f'\n\nWikipedia article section:\n"""\n{string}\n"""'
            if (self.num_tokens(articles + next_article + query) > token_budget):
                break
            else:
                articles += next_article
        return articles

    def appendQuestion(self, question: str):
        self.messages.append({"role":"user", "content":question})
        if self.index:
            articles = self.fetch_related_articles()
            assert self.messages[0]["role"] == "system", "Missing system message"
            self.messages[0] = {"role":"system", "content":re.sub("\\{articles\\}", articles, self.prompt, 1)}

context = ChatContext()

while True:
    question = input(f"\033[95m\033[1m{context.userName}: \033[95m\033[0m")
    if (len(question) == 0):
        print(oneline_help)
        continue
    if (question[0] == "/"):
        key = question[1:]
        if (key == "help"):
            list = ", ".join(f"/{key}" for key in manifests.keys())
            print(f"Extensions: {list}")
            continue
        if (key == "bye"):
            break
        elif (key == "prompt"):
            if (len(context.messages) >= 1 and context.messages[0].get("role")=="system"):
                print(context.messages[0].get("content"))
            continue
        elif (key == "gpt3"):
            context.model = "gpt-3.5-turbo"
            print(f"Model = {context.model}")
            continue
        elif (key == "gpt4"):
            context.model = "gpt-4"
            print(f"Model = {context.model}")
            continue
        elif (key == "sample" and context.manifest != None):
            sample = context.manifest.get("sample") 
            if (sample):
                print(sample)
                context.appendQuestion(sample)
            else:
                continue
        elif (key == "reset"):
            context = ChatContext()
            continue            
        else:
            manifest = manifests.get(key)
            if (manifest):
                context = ChatContext(role=key, manifest = manifest)
                if not os.path.isdir(f"output/{context.role}"):
                    os.makedirs(f"output/{context.role}")
                print(f"Activating: {context.title} (model={context.model}, temperature={context.temperature})")

                if (context.intro):
                    intro = context.intro[random.randrange(0, len(context.intro))]
                    context.messages.append({"role":"assistant", "content":intro})
                    print(f"\033[92m\033[1m{context.botName}\033[95m\033[0m: {intro}")
                continue
            else:            
                print(f"Invalid slash command: {key}")
                continue
    else:
        context.appendQuestion(question)

    # print(f"{messages}")

    response = openai.ChatCompletion.create(model=context.model, messages=context.messages, temperature=context.temperature)
    answer = response['choices'][0]['message']
    res = answer['content']
    print(f"\033[92m\033[1m{context.botName}\033[95m\033[0m: {res}")

    context.messages.append({"role":answer['role'], "content":res})
    with open(f"output/{context.role}/{context.time}.json", 'w') as f:
        json.dump(context.messages, f)
