# 核心交互序列图

## 1. 数据录入序列图

### 1.1 手动录入血压数据

```mermaid
sequenceDiagram
    participant User
    participant CLI as OpenClaw CLI
    participant HM as Health Manager
    participant DB as Database
    participant Analyzer as Analyzer Engine
    
    User->>CLI: openclaw health record bp --systolic 120 --diastolic 80
    CLI->>HM: recordBloodPressure({systolic: 120, diastolic: 80})
    HM->>HM: validateData()
    HM->>HM: normalizeUnits()
    HM->>DB: saveBloodPressureRecord()
    DB-->>HM: recordId
    HM->>Analyzer: triggerAnalysis(recordId)
    Analyzer->>Analyzer: analyzeTrends()
    Analyzer->>Analyzer: checkAnomalies()
    Analyzer-->>HM: analysisResult
    HM-->>CLI: successResponse
    CLI-->>User: "血压记录成功保存"
    
    Note over Analyzer,DB: 异步分析任务
    Analyzer->>DB: updateAnalysisResults()
```

### 1.2 Apple Health 数据同步

```mermaid
sequenceDiagram
    participant Scheduler as Scheduler
    participant HM as Health Manager
    participant AH as Apple Health API
    participant DB as Database
    participant Notifier as Notifier
    
    Scheduler->>HM: syncAppleHealthData()
    HM->>AH: requestAuthorization()
    AH-->>HM: authorizationGranted
    HM->>AH: fetchHealthData(lastSyncTime)
    AH-->>HM: healthData[]
    loop for each data point
        HM->>HM: convertToStandardFormat()
        HM->>DB: saveHealthData()
    end
    HM->>Notifier: notifySyncComplete(count)
    Notifier-->>User: "同步完成：新增XX条记录"
```

## 2. 数据分析序列图

### 2.1 趋势分析请求

```mermaid
sequenceDiagram
    participant User
    participant CLI as OpenClaw CLI
    participant HM as Health Manager
    participant DB as Database
    participant Analyzer as Analyzer Engine
    participant Chart as Chart Generator
    
    User->>CLI: openclaw health trends --metric blood_pressure --period 30d
    CLI->>HM: getTrends('blood_pressure', '30d')
    HM->>DB: queryBloodPressureData(startDate, endDate)
    DB-->>HM: rawData[]
    HM->>Analyzer: calculateTrends(rawData)
    Analyzer->>Analyzer: movingAverage()
    Analyzer->>Analyzer: linearRegression()
    Analyzer-->>HM: trendResult
    HM->>Chart: generateTrendChart(trendResult)
    Chart-->>HM: chartImage
    HM-->>CLI: {trend: result, chart: image}
    CLI-->>User: 显示趋势图表和分析结果
```

### 2.2 异常检测流程

```mermaid
sequenceDiagram
    participant Scheduler as Daily Scheduler
    participant HM as Health Manager
    participant DB as Database
    participant Analyzer as Anomaly Detector
    participant Notifier as Notification System
    
    Scheduler->>HM: runDailyAnomalyCheck()
    HM->>DB: getRecentData(7, ['blood_pressure', 'heart_rate'])
    DB-->>HM: recentData
    HM->>Analyzer: detectAnomalies(recentData)
    
    Analyzer->>Analyzer: thresholdCheck()
    Analyzer->>Analyzer: statisticalOutlierDetection()
    Analyzer->>Analyzer: patternDeviationAnalysis()
    
    Analyzer-->>HM: anomalies[]
    
    alt anomalies found
        HM->>Notifier: sendAlert(anomalies)
        Notifier-->>User: "发现异常数据，请关注"
    else no anomalies
        HM->>DB: logCheckResult('normal')
    end
```

## 3. 报告生成序列图

### 3.1 健康手册生成

```mermaid
sequenceDiagram
    participant User
    participant CLI as OpenClaw CLI
    participant HM as Health Manager
    participant DB as Database
    participant Template as Template Engine
    participant Chart as Chart Generator
    participant PDF as PDF Generator
    
    User->>CLI: openclaw health handbook
    CLI->>HM: generateHealthHandbook()
    
    HM->>DB: getUserProfile()
    DB-->>HM: userProfile
    HM->>DB: getHealthData(allTime)
    DB-->>HM: healthData
    HM->>DB: getAnalysisResults()
    DB-->>HM: analysisResults
    
    par 并行处理
        HM->>Chart: generateSummaryCharts(healthData)
        Chart-->>HM: charts[]
        HM->>Template: renderTemplate('handbook', data)
        Template-->>HM: renderedContent
    end
    
    HM->>PDF: convertToPDF(renderedContent, charts)
    PDF-->>HM: pdfBuffer
    HM->>HM: saveFile(pdfBuffer, 'health-handbook.pdf')
    HM-->>CLI: {filepath: '...', size: '...'}
    CLI-->>User: "健康手册已生成: path/to/handbook.pdf"
```

## 4. 提醒系统序列图

### 4.1 用药提醒触发

```mermaid
sequenceDiagram
    participant Scheduler as Reminder Scheduler
    participant HM as Health Manager
    participant DB as Database
    participant Notifier as Notification System
    participant User
    
    Scheduler->>HM: checkReminders()
    HM->>DB: getDueReminders(currentTime)
    DB-->>HM: dueReminders[]
    
    loop for each reminder
        HM->>Notifier: sendReminder(reminder)
        Notifier-->>User: "用药提醒：请服用降压药10mg"
        
        alt user acknowledges
            User->>Notifier: acknowledge()
            Notifier->>HM: markAsAcknowledged(reminder.id)
            HM->>DB: updateReminderStatus('acknowledged')
        end
        
        alt user snoozes
            User->>Notifier: snooze(30)
            Notifier->>HM: rescheduleReminder(reminder.id, +30min)
            HM->>DB: updateReminderSchedule()
        end
    end
```

### 4.2 智能建议生成

```mermaid
sequenceDiagram
    participant Scheduler as Weekly Scheduler
    participant HM as Health Manager
    participant DB as Database
    participant Analyzer as Analysis Engine
    participant Recommender as Recommender System
    
    Scheduler->>HM: generateWeeklyRecommendations()
    HM->>DB: getWeeklyData()
    DB-->>HM: weeklyData
    HM->>Analyzer: analyzeWeeklyPatterns(weeklyData)
    Analyzer->>Analyzer: identifyImprovementAreas()
    Analyzer->>Analyzer: evaluateGoalProgress()
    Analyzer-->>HM: analysisInsights
    HM->>Recommender: generateRecommendations(analysisInsights)
    Recommender->>Recommender: applyRuleEngine()
    Recommender->>Recommender: personalizeForUser()
    Recommender-->>HM: recommendations[]
    HM->>DB: saveRecommendations(recommendations)
    HM->>HM: formatForDisplay(recommendations)
    HM-->>User: "本周健康建议：1. 增加有氧运动 2. 控制钠摄入"
```

## 5. 错误处理序列图

### 5.1 数据验证失败

```mermaid
sequenceDiagram
    participant User
    participant CLI as OpenClaw CLI
    participant HM as Health Manager
    participant Validator as Data Validator
    
    User->>CLI: openclaw health record bp --systolic 300 --diastolic 200
    CLI->>HM: recordBloodPressure({systolic: 300, diastolic: 200})
    HM->>Validator: validateBloodPressure(300, 200)
    Validator->>Validator: checkRange(0-300)
    Validator->>Validator: checkRatio(systolic/diastolic)
    Validator-->>HM: validationError("血压值超出合理范围")
    HM-->>CLI: validationError
    CLI-->>User: "错误：血压值超出合理范围，请检查输入"
    
    Note over User,CLI: 提供修正建议
    CLI->>User: "正常收缩压范围：90-140mmHg，舒张压：60-90mmHg"
```

## 交互状态说明

### 关键状态转移

1. **数据录入状态**:
   ```
   IDLE → VALIDATING → PROCESSING → SAVING → ANALYZING → COMPLETE
           ↓
         ERROR → RETRY/CANCEL
   ```

2. **分析任务状态**:
   ```
   PENDING → FETCHING_DATA → ANALYZING → GENERATING_OUTPUT → COMPLETE
               ↓
             TIMEOUT → RETRY/ABORT
   ```

3. **提醒生命周期**:
   ```
   SCHEDULED → DUE → SENT → ACKNOWLEDGED/SNOOZED → COMPLETED
       ↓
     CANCELLED/EXPIRED
   ```

### 超时和重试机制

- **数据同步**: 30秒超时，最多重试3次
- **分析任务**: 5分钟超时，可后台继续
- **文件生成**: 2分钟超时，支持断点续传
- **API调用**: 15秒超时，指数退避重试

---

这些序列图展示了 Health Manager Skill 的核心交互流程，可以作为开发实现时的参考。