# truck-safety-vision-system
Edge AI computer vision system using Raspberry Pi 5 and Edge Impulse to detect tailgating by CMVs, capture of DOT numbers with automatic reporting to safety departments and eventually to DOT/ FMCSA to affect CSA real-time.
# Truck Safety Vision System

**Edge AI system to detect and report aggressive driving by commercial vehicles**

## 🚛 The Problem

As a commercial driver, I witness dangerous tailgating by 18-wheelers daily. These drivers operate with impunity, even in front of law enforcement, creating serious safety risks for everyone on the road. Current enforcement is reactive - officers only get involved after crashes occur. 

Many companies have systems that detect dangerous driving by their own employees, We need systems that detect dangerous drivers in the vicinity of a company vehicle.

Aggressive commercial drivers need accountability, and companies need better visibility into their drivers' behavior on the road.

## 💡 The Solution

An Edge AI system that:
- **Detects** tailgating behavior (following distance of one car length or less) using computer vision
- **Captures** DOT numbers from passing vehicles using OCR
- **Reports** incidents directly to company safety departments
- **Eventually integrates** with DOT/FMCSA systems to affect CSA scores in real-time

### Future Vision
Create a distributed network where multiple trucks running this system contribute to a real-time safety intelligence platform, making dangerous driving patterns visible and consequential.

## 🛠️ Tech Stack

- **Hardware**: Raspberry Pi 5 (8GB) with wide-angle camera modules
- **ML Platform**: Edge Impulse for model training and deployment
- **Computer Vision**: Object detection + distance estimation for tailgating detection, OCR for DOT number capture
- **Storage**: High-endurance microSD (initially), future cloud integration

## 📍 Current Status

**Phase 0: Setup & Learning** ✅ (You are here!)
- Repository created
- Hardware acquired
- Starting with single left-side camera for proof of concept

**Phase 1: Basic Detection** 🔄 (Next)
- Train model to identify 18-wheelers
- Implement tailgating detection algorithm
- Test on real road footage

**Phase 2: DOT Capture**
- OCR for DOT number recognition
- Validate accuracy under various conditions

**Phase 3: Reporting System**
- Automated report generation
- Company safety department integration

**Phase 4: Network Effect**
- Multi-device data aggregation platform
- DOT/FMCSA integration exploration

## 🤝 Contributing

This project is in early stages and I'm **building in public**. I'm learning as I go - coming from a trucking background with basic web dev skills, not a CS degree.

**Ways to contribute:**
- Computer vision expertise
- Raspberry Pi optimization tips
- Legal/regulatory guidance on DOT integration
- Documentation improvements
- Testing and feedback

*Note: Core software will be source-available. Commercial licensing to be determined. Contributions welcome under CLA.*

## 📚 Building in Public

Follow the journey:
- **GitHub**: Right here - watch for commits and issues
- **YouTube**: http://www.youtube.com/@ScottSager_Dev1 (coming soon)
- **X/Twitter**: https://x.com/scottsagerdev1
- **LinkedIn**: http://linkedin.com/in/scott-sager-b94273361


## 👤 About Me

I'm a commercial truck driver with a hightened awareness of dangerous drivers that endanger public safety. My ultimate goal is to save lives. I have basic coding skills (freeCodeCamp responsive web design, published Bubble.io app, some Linux/Git) and a passion, learned about late in life, for using technology to solve real problems. This is my first hardware + AI project, and I'm documenting everything along the way. It'll be slow going with minimal time, but looking forward to learning and meeting interesting, likeminded individuals along the way.

## 📄 License

Source-available for personal, educational, and research use. Commercial use requires separate licensing. See LICENSE file for details.

---

**Status**: 🟢 Active Development | **Last Updated**: Nov. 25th, 2025
