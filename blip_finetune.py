import torch
import os
import pandas as pd
from PIL import Image
from torch.utils.data import Dataset, DataLoader, random_split
from torch.cuda.amp import autocast, GradScaler
from transformers import BlipProcessor, BlipForConditionalGeneration
from torch.optim.lr_scheduler import CosineAnnealingLR
import warnings
from config import BLIP_MODEL_base_PATH
warnings.filterwarnings('ignore')

# ==================== 配置参数 ====================
DATA_DIR = "./poster_data"
METADATA_FILE = f"{DATA_DIR}/metadata.csv"
OUTPUT_DIR = "./blip-finetuned-poster"

BATCH_SIZE = 2
EPOCHS = 30
LEARNING_RATE = 3e-5
MAX_LENGTH = 100
NUM_WORKERS = 0

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"使用设备: {device}")


# ==================== 数据集类 ====================
class PosterDataset(Dataset):
    def __init__(self, csv_file, processor, data_dir):
        self.data = pd.read_csv(csv_file)
        self.processor = processor
        self.data_dir = data_dir
        print(f"加载 {len(self.data)} 条样本")

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        row = self.data.iloc[idx]
        img_path = os.path.join(self.data_dir, row['file_name'])
        try:
            image = Image.open(img_path).convert('RGB')
        except:
            image = Image.new('RGB', (224, 224), color='white')
        caption = str(row['caption'])
        return {"image": image, "caption": caption}


def collate_fn(batch):
    images = [item["image"] for item in batch]
    captions = [item["caption"] for item in batch]

    inputs = processor(
        images=images,
        text=captions,
        padding="max_length",
        truncation=True,
        max_length=150,
        return_tensors="pt"
    )
    inputs["labels"] = inputs["input_ids"].clone()

    # 只保留模型需要的键
    allowed_keys = ["input_ids", "attention_mask", "pixel_values", "labels"]
    return {k: v for k, v in inputs.items() if k in allowed_keys}


# ==================== 加载模型 ====================
print("加载模型...")
processor = BlipProcessor.from_pretrained(BLIP_MODEL_base_PATH)
model = BlipForConditionalGeneration.from_pretrained(BLIP_MODEL_base_PATH)
model.to(device)

# 打印可训练参数
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"可训练参数: {trainable:,} / {total:,} ({100 * trainable / total:.1f}%)")

# ==================== 创建数据集 ====================
full_dataset = PosterDataset(METADATA_FILE, processor, DATA_DIR)
train_size = int(0.8 * len(full_dataset))
val_size = len(full_dataset) - train_size
train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])
print(f"训练集: {train_size}, 验证集: {val_size}")

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn,
                          num_workers=NUM_WORKERS)
val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn,
                        num_workers=NUM_WORKERS)

# ==================== 训练配置 ====================
optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
scaler = GradScaler()
total_steps = EPOCHS * len(train_loader)
scheduler = CosineAnnealingLR(optimizer, T_max=total_steps)


# ==================== 验证函数 ====================
def evaluate(model, val_loader, device):
    model.eval()
    total_loss = 0
    with torch.no_grad():
        for batch in val_loader:
            inputs = {k: v.to(device) for k, v in batch.items()}
            with autocast():
                outputs = model(**inputs)
            total_loss += outputs.loss.item()
    model.train()
    return total_loss / len(val_loader)


# ==================== 训练循环 ====================
print("\n开始训练...")
best_val_loss = float('inf')

for epoch in range(EPOCHS):
    model.train()
    epoch_loss = 0

    for batch_idx, batch in enumerate(train_loader):
        inputs = {k: v.to(device) for k, v in batch.items()}

        with autocast():
            outputs = model(**inputs)
            loss = outputs.loss

        optimizer.zero_grad()
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        epoch_loss += loss.item()

        if batch_idx % 10 == 0:
            print(f"Epoch {epoch + 1:2d}/{EPOCHS} | Batch {batch_idx:3d}/{len(train_loader)} | Loss: {loss.item():.4f}")

    avg_train_loss = epoch_loss / len(train_loader)
    avg_val_loss = evaluate(model, val_loader, device)
    scheduler.step()

    print(
        f"📊 Epoch {epoch + 1} | 训练Loss: {avg_train_loss:.4f} | 验证Loss: {avg_val_loss:.4f} | LR: {scheduler.get_last_lr()[0]:.2e}")

    if avg_val_loss < best_val_loss:
        best_val_loss = avg_val_loss
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        model.save_pretrained(OUTPUT_DIR)
        processor.save_pretrained(OUTPUT_DIR)
        print(f"  ✅ 保存最佳模型")

print(f"\n🎉 完成！最佳验证Loss: {best_val_loss:.4f}")

# ==================== 测试 ====================
print("\n测试生成效果...")
model.eval()
test_batch = next(iter(val_loader))
pixel_values = test_batch["pixel_values"][0:1].to(device)

with torch.no_grad():
    with autocast():
        generated_ids = model.generate(
            pixel_values=pixel_values,
            max_new_tokens=100,
            num_beams=4,
            repetition_penalty=1.2
        )
        result = processor.decode(generated_ids[0], skip_special_tokens=True)

print(f"生成描述: {result}")