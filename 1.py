import random
import string

COMMON_NAMES = [
    "adam", "alex", "andy", "anna", "beth", "brad", "carl", "cora",
    "dale", "dana", "dean", "dora", "earl", "edna", "emma", "eric",
    "fern", "finn", "fred", "gail", "gary", "gene", "glen", "greg",
    "hank", "hans", "hope", "hugh", "igor", "ivan", "jack", "jade",
    "jake", "jane", "jean", "jere", "jess", "joan", "joel", "john",
    "jose", "judy", "june", "karl", "kate", "kent", "kirk", "kurt",
    "lana", "leon", "lily", "lisa", "lois", "luke", "lynn", "marc",
    "mark", "mary", "matt", "mike", "milo", "neil", "nick", "nina",
    "noel", "nora", "olga", "omar", "otto", "paul", "pete", "phil",
    "remi", "rene", "rhea", "rick", "rita", "rob", "rosa", "ross",
    "ruby", "ruth", "ryan", "sara", "sean", "seth", "stan", "sue",
    "tara", "ted", "tina", "todd", "tony", "troy", "vera", "wade",
    "walt", "ward", "will", "yuri", "zane", "zara"
]


def generate_prefix():
    name = random.choice(COMMON_NAMES)
    target_length = random.choice([6, 7])
    padding_length = min(max(target_length - len(name), 1), 3)
    noise = ''.join(random.choices(string.ascii_lowercase, k=padding_length))
    return (name + noise)[:target_length]


def generate_suffix(length=6):
    chars = string.ascii_lowercase + string.digits
    while True:
        suffix = ''.join(random.choices(chars, k=length))
        if any(c.isalpha() for c in suffix) and any(c.isdigit() for c in suffix):
            return suffix


def generate_fake_email():
    return f"{generate_prefix()}-{generate_suffix()}@yahoo.com"


# ========== 配置区 ==========
NUM = 50          # 生成数量，按需修改
OUTPUT_FILE = "emails.txt"  # 输出文件名

# ========== 生成并写入文件 ==========
with open(OUTPUT_FILE, "w") as f:
    for _ in range(NUM):
        f.write(generate_fake_email() + "\n")

print(f"已生成 {NUM} 条，写入 {OUTPUT_FILE}")
