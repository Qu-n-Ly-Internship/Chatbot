# Hướng Dẫn Tổng Quan: React, Java Spring, SQL/MySQL

File này giúp thực tập sinh và ứng viên hiểu các công nghệ chính được sử dụng trong công ty và cách tự học chúng.

---

## 1. React

### Giới thiệu
- React là **thư viện JavaScript** dùng để xây dựng giao diện người dùng (UI) cho ứng dụng web.  
- React giúp tạo các **component tái sử dụng**, quản lý trạng thái (state) và render hiệu quả.

### Ứng dụng
- Frontend web application: dashboard, landing page, form, SPA (Single Page Application).  
- Mobile app (với React Native).

### Từ khóa/khái niệm quan trọng
- JSX, Components, Props, State, Hooks (useState, useEffect)  
- Virtual DOM, Event Handling, Lifecycle Methods  
- Router, Redux / Context API, Axios / Fetch API  
- Testing: Jest, React Testing Library  

### Gợi ý học tập
- Bắt đầu với tutorial chính thức: [https://reactjs.org](https://reactjs.org)  
- Làm mini-project: Todo app, blog app, dashboard đơn giản  
- Thực hành **component-based development** và **state management**

---

## 2. Java Spring (Spring Boot)

### Giới thiệu
- Spring Boot là **framework Java** giúp xây dựng các ứng dụng backend nhanh chóng và chuẩn hóa.  
- Hỗ trợ cấu hình tự động, dependency management, REST API, database connection.

### Ứng dụng
- Backend service cho web app hoặc mobile app.  
- REST API, Authentication & Authorization, Microservices.

### Từ khóa/khái niệm quan trọng
- Spring Boot, Spring MVC, REST Controller  
- Dependency Injection (DI), Inversion of Control (IoC)  
- JPA / Hibernate, Repository, Entity  
- Service Layer, DTO, Exception Handling  
- Security: Spring Security, JWT  
- Testing: JUnit, Mockito

### Gợi ý học tập
- Bắt đầu từ tutorial Spring Boot chính thức: [https://spring.io/projects/spring-boot](https://spring.io/projects/spring-boot)  
- Thực hành tạo API CRUD kết nối MySQL  
- Tìm hiểu **RESTful API design** và **layered architecture**

---

## 3. SQL / MySQL

### Giới thiệu
- SQL (Structured Query Language) là ngôn ngữ dùng để **tạo, truy vấn, và quản lý dữ liệu** trong database.  
- MySQL là một **Relational Database Management System (RDBMS)** phổ biến.

### Ứng dụng
- Lưu trữ dữ liệu cho ứng dụng web, mobile, backend.  
- Quản lý thông tin người dùng, sản phẩm, báo cáo, lịch sử giao dịch.

### Từ khóa/khái niệm quan trọng
- Database, Table, Column, Row  
- CRUD: Create, Read, Update, Delete  
- Primary Key, Foreign Key, Index  
- Joins (INNER, LEFT, RIGHT), Aggregate Functions (SUM, COUNT, AVG)  
- Transactions, Stored Procedures, Views

### Gợi ý học tập
- Thực hành trên MySQL Workbench, DBeaver hoặc phpMyAdmin  
- Tạo database nhỏ, bảng user/product/order  
- Viết query CRUD, joins, group by, order by  
- Học cách kết nối Spring Boot với MySQL bằng JPA/Hibernate

---

## 4. Lời khuyên cho thực tập sinh

- Bắt đầu học **từng công nghệ một** và làm các mini-project nhỏ.  
- Tập trung vào **React cho frontend**, **Spring Boot cho backend**, **MySQL cho lưu trữ dữ liệu**.  
- Tìm hiểu workflow thực tế: **Git + Docker + CI/CD + IDE**.  
- Tích hợp cả ba: tạo một project nhỏ full-stack (React + Spring Boot + MySQL) để hiểu cách các phần kết nối.  
- Sử dụng từ khóa trên để tìm tutorial, video, documentation và ví dụ thực hành.

---

> **Tip:** Các công cụ này thường đi cùng nhau trong các dự án thực tế, nên việc thực hành kết hợp sẽ giúp bạn nắm workflow đầy đủ từ frontend → backend → database.
