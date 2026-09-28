# Tìm hiểu Docker + WSL2

---

## 1. Lý thuyết

### 1. Hạ tầng nền tảng (Host & Infrastructure)

#### Windows Subsystem for Linux (WSL2)

**WSL2** là một tính năng của Microsoft tích hợp vào Windows, cho phép nhà phát triển chạy môi trường GNU/Linux **trực tiếp trên Windows** mà không cần cài đặt song song hai hệ điều hành (Dual-boot) hoặc sử dụng các phần mềm ảo hóa bên thứ ba như VMware hay VirtualBox.

- **Lợi ích:** Mang lại khả năng tương thích 100% với các lệnh gọi hệ thống của Linux, tăng tốc độ xử lý của hệ thống tệp tin và hỗ trợ đầy đủ cho các công nghệ như Docker.

---

### 2. Nền tảng Container quản lý (The Container Platform)

#### Docker

**Docker** là một nền tảng mã nguồn mở cho phép đóng gói ứng dụng và tất cả các thành phần phụ thuộc của nó (thư viện, môi trường cấu hình...) vào trong một đơn vị duy nhất gọi là **Container**.

- **Cách thức hoạt động:** Khác với máy ảo (Virtual Machine) cần một hệ điều hành khách (Guest OS) riêng biệt làm tiêu tốn nhiều tài nguyên, Docker Container chia sẻ chung nhân hệ điều hành (Kernel) của máy host. Nó cô lập ứng dụng ở tầng tiến trình (Process isolation).
- **Lợi ích:** Đảm bảo ứng dụng chạy đồng nhất ở mọi môi trường (từ máy lập trình viên cho đến máy chủ thử nghiệm và hệ thống production thực tế) theo nguyên tắc "Viết một lần, chạy mọi nơi".

#### Sự kết hợp giữa Docker và WSL2

- **Kiến trúc tối ưu:** Trước đây, Docker Desktop trên Windows phải chạy thông qua một máy ảo Hyper-V cồng kềnh, chiếm dụng cố định một lượng tài nguyên RAM và CPU lớn. Với WSL2, Docker Daemon chạy trực tiếp trên một nhân Linux tinh giản do Microsoft tối ưu hóa.
- **Tốc độ vượt trội:** Thời gian khởi động Docker Daemon và các container giảm từ vài phút xuống chỉ còn vài giây. Hiệu năng đọc/ghi tệp tin (File System I/O) giữa Windows và Linux nhanh hơn gấp nhiều lần.
- **Cấp phát tài nguyên động:** WSL2 cho phép Docker sử dụng bao nhiêu RAM/CPU tùy ý theo nhu cầu thực tế và tự động hoàn trả lại cho Windows khi container dừng hoạt động.

---

### 3. Bản thiết kế và Cấu hình tự động (Blueprints & Automation)

#### Dockerfile

Dockerfile là một **tập tin văn bản thô** (không có phần mở rộng) chứa một tập hợp các chỉ dẫn nối tiếp nhau để Docker tự động biên dịch (build) ra một Docker Image đóng gói toàn bộ mã nguồn và môi trường chạy ứng dụng của bạn.

- **Cơ chế Layer (Tầng):** Mỗi câu lệnh trong Dockerfile (như RUN, COPY) tạo ra một lớp dữ liệu trung gian có thể được ghi nhớ vào bộ đệm (cache). Nếu bạn không sửa đổi gì ở lớp đó, Docker sẽ dùng lại cache để tăng tốc độ build cho lần sau.
- **Biến số môi trường và Bảo mật:** Các chỉ dẫn như ARG và ENV giúp truyền tham số linh hoạt nhưng cần cẩn thiện để tránh lộ mật khẩu, API key vào trong Image công khai.

#### Docker Compose

Docker Compose là một công cụ giúp định nghĩa và điều phối hệ thống gồm nhiều Container (Multi-container Docker applications). Thay vì phải gõ hàng chục lệnh `docker run` phức tạp với đủ loại tham số mạng, ổ đĩa cho từng container, bạn chỉ cần mô tả toàn bộ kiến trúc hạ tầng trong một file duy nhất cấu trúc theo định dạng YAML.

- **Quản lý tập trung:** Toàn bộ vòng đời ứng dụng (tạo mạng kết nối, gán phân vùng ổ đĩa, biến môi trường, thứ tự khởi chạy giữa các dịch vụ) được cấu hình rõ ràng trong file `docker-compose.yml`.
- **Tự động tạo Network chung:** Tất cả các container (trong file compose gọi là services) được khai báo trong cùng một file Compose sẽ tự động tham gia vào một mạng chung biệt lập. Chúng có thể gọi nhau qua lại bằng chính Tên Service (Service Name) nhờ cơ chế DNS nội bộ của Docker.

---

### 4. Thực thể đóng gói và Thực thi (Artifacts & Runtimes)

#### Docker Image

**Docker Image** là một gói phần mềm tĩnh, đóng gói sẵn (Read-only) chứa toàn bộ mã nguồn, môi trường thực thi (runtime) và các thư viện cần thiết để ứng dụng chạy được. Bạn có thể hình dung Image giống như một file cài đặt phần mềm (.exe) hoặc một chiếc khuôn đúc bánh. Vì là tệp tĩnh, dữ liệu bên trong Image không bao giờ thay đổi và nó không thể tự chạy mà chỉ dùng để khởi tạo **Container**.

#### Docker Container

**Docker Container** là một thực thể sống (Runtime Instance) được khởi tạo từ **Docker Image**. Nếu Image là file cài đặt phần mềm thì Container chính là phần mềm đang hoạt động thực tế. Container chạy cô lập như một tiến trình trực tiếp trên nhân hệ điều hành của máy host mà không cần hệ điều hành riêng. Nó có một tầng dữ liệu tạm thời cho phép đọc-ghi (Read-Write) khi chạy, nhưng mọi dữ liệu này sẽ mất đi nếu container bị xóa mà không cấu hình **Volume** lưu trữ.

---

### 5. Cơ chế lưu trữ bền vững (Persistent Storage)

#### Docker Volume

**Docker Volume** là cơ chế lưu trữ dữ liệu độc lập hoàn toàn với vòng đời của **Container**, được quản lý trực tiếp bởi Docker trên hệ điều hành host. Khi Container bị dừng hoặc xóa, toàn bộ dữ liệu lưu trong Volume vẫn được bảo toàn nguyên vẹn để gắn (mount) sang Container mới. Đây là giải pháp tối ưu giúp lưu trữ dữ liệu bền vững cho các ứng dụng như cơ sở dữ liệu (Database), đồng thời tăng hiệu năng đọc/ghi (I/O) nhờ bỏ qua tầng dữ liệu tạm thời của Container.

## 2. Cài đặt

### Bước 1: Kích hoạt WSL2 trên Windows

1. Mở PowerShell với quyền Admin (Run as Administrator).
2. Chạy câu lệnh sau để cài đặt WSL và bản phân phối Ubuntu mặc định:

```bash
    wsl --install
```

3. Nếu máy bạn đã cài WSL từ trước, hãy đảm bảo cập nhật lên phiên bản nhân mới nhất:

```bash
    wsl --update
```

4. Khởi động lại máy tính nếu hệ thống yêu cầu. Sau khi khởi động lại, một cửa sổ Ubuntu sẽ hiện ra để bạn thiết lập Username và Password.

### Bước 2: Kiểm tra phiên bản WSL

Đảm bảo rằng bản phân phối Linux của bạn đang chạy trên nền tảng WSL 2 bằng lệnh:

```bash
    wsl --list --verbose
```

hoặc

```bash
    wsl -l -v
```

(Nếu cột VERSION hiển thị là 1, hãy chuyển đổi bằng lệnh:

```bash
    wsl --set-version <tên_bản_phân_phối> 2
```

)

### Bước 3: Cài đặt Docker Engine trực tiếp trong Ubuntu

1. Cập nhật danh sách gói và cài đặt các công cụ tải thiết yếu:

```bash
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
```

2. Thêm khóa GPG chính thức của Docker:

```bash
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
```

3. Thiết lập kho lưu trữ (repository) ổn định cho Docker:

```bash
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

4. Tiến hành cài đặt Docker Engine, CLI và Docker Compose plugin:

```bash
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### Bước 4: Khởi động dịch vụ và Cấu hình quyền không cần sudo

1. Kích hoạt và khởi động Docker daemon bên trong môi trường WSL2:

```bash
    sudo service docker start
```

2. Thêm User hiện tại của bạn vào nhóm `docker` để có thể chạy lệnh mà không cần gõ `sudo`:

```bash
    sudo usermod -aG docker $USER
```

### Mở rộng 1: Cấu trúc file docker compose mẫu (kết nối với CSDL Vector Qdrant)

```yaml
services:
  web-app:
    build: .
    container_name: node-web-service
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - /app/node_modules
    environment:
      - QDRANT_HOST=vector-db
      - QDRANT_PORT=6333
    depends_on:
      - vector-db

  vector-db:
    image: qdrant/qdrant:latest
    container_name: qdrant-vector-service
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage

volumes:
  qdrant_storage:
```

#### Giải thích thuộc tính

- `services`: Danh sách các container cấu thành hệ thống (web-app và vector-db).
- `build: .`: Chỉ thị cho Compose biết cần phải tự động tìm Dockerfile ở thư mục hiện tại để build Image cho dịch vụ web-app.
- `volumes` (Dưới dịch vụ web-app): Cơ chế Bind Mount mở rộng giúp đồng bộ code theo thời gian thực. Sửa code ở máy Windows/WSL2 thì container nhận luôn mà không cần build lại Image. Dòng /app/node_modules để ẩn thư mục này đi, tránh bị ghi đè bởi thư mục trống từ máy host.
- `environment`: Khai báo biến môi trường. Chú ý giá trị QDRANT_HOST=vector-db, chuỗi vector-db chính là tên của dịch vụ bên dưới. Node.js sẽ kết nối trực tiếp qua tên này mà không cần biết IP của container Qdrant là gì.
- `depends_on`: Ràng buộc thứ tự khởi chạy. Container Qdrant phải lên trước thì container Web mới được khởi động.
- `volumes` (Cấp ngoài cùng): Khai báo một Docker Volume tên là qdrant_storage có tính chất lâu bền để giữ lại toàn bộ dữ liệu vector của Qdrant ngay cả khi hệ thống bị tắt hoàn toàn.

### Mở rộng 2: Cấu trúc file Dockerfile

```Dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package\*.json ./

RUN npm install

COPY . .

EXPOSE 3000

CMD ["node", "server.js"]
```

#### Giải thích chỉ dẫn:

- `FROM`: Định nghĩa Image nền (Base Image). Ở đây dùng Node.js bản 18 chạy trên hệ điều hành Linux Alpine siêu nhẹ để giảm dung lượng file.
- `WORKDIR`: Tạo và chuyển thư mục làm việc hiện hành bên trong container thành `/app`.
- `COPY package*.json ./` : Chép các file định nghĩa thư viện trước. Điều này giúp tận dụng Docker cache; nếu file này không đổi, Docker sẽ bỏ qua bước RUN `npm install` ở lần build sau.
- `RUN`: Thực thi lệnh cài đặt thư viện ngay trong quá trình build Image.
- `COPY . . `: Chép toàn bộ mã nguồn còn lại từ máy Host vào thư mục `/app` của Image.
- `EXPOSE`: Khai báo cổng mà container sẽ lắng nghe khi chạy (mang tính chất tài liệu hướng dẫn, chưa thực sự mở cổng ra máy ngoài).
- `CMD`: Lệnh mặc định sẽ chạy khi container được khởi động (khác với RUN là chạy trong lúc build).

## 3. Các tác vụ cơ bản (Demo)

Sau khi cài đặt xong, bạn có thể mở Terminal (ưu tiên sử dụng Git Bash) để thực hiện các tác vụ sau.

### Kiểm tra trạng thái Docker

Đảm bảo Docker đã chạy thành công và xem phiên bản hiện tại:

```sh
docker --version
```

hoặc

```sh
docker -v
```

và

```sh
docker info
```

### Khởi động nhanh một Container (One-command startup)

Tải và chạy một container Web Server Nginx chạy ngầm trên cổng 8080 của máy vật lý:

```sh
docker run -d -p 8080:80 --name web-demo nginx:alpine
```

Ý nghĩa các tham số:

- `-d`: Chạy ngầm (Detached mode), giải phóng cửa sổ Terminal.
- `-p 8080:80`: Ánh xạ cổng 8080 của máy Host (Windows) vào cổng 80 bên trong Container.
- `--name web-demo`: Đặt tên cho container để dễ quản lý.

### Kiểm tra danh sách Container

Xem các container đang chạy:

```sh
docker ps
```

Xem tất cả các container (bao gồm cả các container đã dừng):

```sh
docker ps -a
```

### Xem log (nhật ký) của Container

Theo dõi các lượt truy cập hoặc lỗi hệ thống của container web-demo:

```sh
docker logs web-demo
```

### Truy cập vào bên trong Container

Mở Terminal bên trong môi trường Linux thu nhỏ của Container để cấu hình hoặc kiểm tra file:

```sh
docker exec -it web-demo sh
```

(Gõ exit để thoát ra ngoài Terminal của máy Host)

### Dừng và Xóa Container

Khi không còn sử dụng, tiến hành dừng container:

```sh
docker stop web-demo
```

Xóa hoàn toàn container khỏi hệ thống để giải phóng tài nguyên:

```sh
docker rm web-demo
```

Xóa Docker Image (bản cài đặt mẫu của Nginx) nếu không cần dùng lại:

```sh
docker rmi nginx:alpine
```

## Các tác vụ của Docker compose

Khởi chạy toàn bộ hệ thống ở chế độ chạy ngầm (Sẽ tự động build Image nếu chưa có):

```sh
docker compose up -d
```

Khởi chạy toàn bộ hệ thống ở chế độ chạy ngầm (Cập nhật thêm vào image đã có):

```sh
docker compose up -d --build
```

Xem trạng thái và danh sách các container do Compose quản lý:

```sh
docker compose ps
```

Theo dõi log thời gian thực của toàn bộ hệ thống (hoặc chỉ định tên service ở cuối):

```sh
docker compose logs -f
```

Dừng toàn bộ hệ thống, tắt các container nhưng vẫn giữ lại Volume dữ liệu:

```sh
docker compose down
```

Dừng hệ thống đồng thời xóa sạch toàn bộ Container, Mạng và các Volume dữ liệu đi kèm:

```sh
docker compose down -v
```

## Tổng Hợp Nhanh

| Concept            | Một câu mô tả                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------------- |
| **Docker**         | Nền tảng mã nguồn mở cho phép đóng gói ứng dụng và tất cả các thành phần phụ thuộc của nó             |
| **WSL2**           | Hệ thống con Linux thế hệ 2 trên Windows, chạy True Linux Kernel siêu nhẹ để tối ưu hiệu năng.        |
| **Docker Daemon**  | Tiến trình chạy ngầm làm nhiệm vụ quản lý, xây dựng và vận hành các Docker tài nguyên.                |
| **Image**          | Bản đóng gói tĩnh chứa toàn bộ mã nguồn, thư viện và môi trường ứng dụng (chỉ đọc - Read-only).       |
| **Container**      | Một thực thể (Instance) đang chạy của một Image, hoạt động cô lập như một tiến trình máy tính.        |
| **Volume**         | Cơ chế lưu trữ dữ liệu lâu bền do Docker quản lý, độc lập hoàn toàn với vòng đời của Container.       |
| **Dockerfile**     | File chỉ dẫn các bước cấu hình tuần tự để tự động build từ mã nguồn ra một Docker Image.              |
| **Docker Compose** | Công cụ cấu hình YAML giúp quản lý, liên kết mạng và điều phối hệ thống gồm nhiều Container cùng lúc. |

## Checklist tự kiểm tra

| #   | Câu hỏi tự kiểm tra kiến thức                                                                                                                                  |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Tại sao để mã nguồn ở ổ `C:/Projects` lại làm Docker trên WSL2 chạy chậm hơn khi để ở thư mục nội bộ Linux `/home/ubuntu/`?                                    |
| 2   | Phân biệt sự khác nhau về mục đích sử dụng giữa lệnh RUN và lệnh CMD bên trong một Dockerfile?                                                                 |
| 3   | "Trong file `docker-compose.yml`, bằng cách nào ứng dụng Node.js có thể kết nối được tới Qdrant Container mà không cần điền IP tĩnh?"                          |
| 4   | Điểm khác biệt lớn nhất khi tắt hệ thống bằng lệnh `docker compose down` so với `docker compose down -v` là gì?                                                |
| 5   | "Tùy chọn ""Use the WSL 2 based engine"" trong cài đặt Docker Desktop giải quyết bài toán gì so với kiến trúc cũ chạy qua Hyper-V?"                            |
| 6   | "Khi container bị dừng (`docker stop`) và xóa đi (`docker rm`), dữ liệu được tạo ra trong container lúc hoạt động có bị mất không? Làm thế nào để giải quyết?" |
| 7   | Docker cache hoạt động như thế nào khi build Dockerfile? Tại sao nên `COPY package.json` trước khi `COPY .` toàn bộ mã nguồn?                                  |
