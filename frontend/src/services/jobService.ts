import apiClient from './api'

export interface ResumeProfile {
  id: string
  name: string
  targetRole: string
  yearsOfExperience: number
  educationLevel: string
  currentCity: string
  targetCity: string
  expectedSalary: string
  rawText?: string
  parsedData?: any
  score: number
  scoreDetails?: {
    completeness?: number
    clarity?: number
    impact?: number
    relevance?: number
    total?: number
    suggestions?: string[]
  }
  isDefault: boolean
  versionsCount?: number
  versions?: ResumeVersion[]
  updatedAt?: string
  createdAt?: string
}

export interface ResumeVersion {
  id: string
  versionName: string
  targetJobTitle: string
  customContent: any
  starEnhancedProjects: any[]
  tailoredJd?: string
  score: number
  updatedAt?: string
}

export interface JobOpportunity {
  id: string
  title: string
  company: string
  companyLogo?: string
  city: string
  salaryMin: number | null
  salaryMax: number | null
  salaryUnit: string
  salaryStatus: 'known' | 'negotiable' | 'unknown' | string
  educationReq: string
  experienceReq: string
  jobType: string
  sourcePlatform: string
  sourceUrl?: string
  externalJobId?: string | null
  sourceUrlCanonical?: string
  lastSeenAt?: string
  detailStatus?: 'pending' | 'success' | 'failed' | 'skipped' | string
  detailError?: string
  detailAttemptedAt?: string
  jdText?: string
  companyTags?: string[]
  requiredSkills?: string[]
  preferredSkills?: string[]
  responsibilities?: string[]
  benefits?: string[]
  createdAt?: string
}

export interface JobMatchReport {
  id?: string
  resumeId: string
  jobId: string
  overallScore: number
  skillMatchScore: number
  experienceMatchScore: number
  educationMatchScore: number
  matchLevel: string
  matchedSkills: string[]
  missingSkills: string[]
  strongPoints: string[]
  weakPoints: string[]
  starProjectSuggestions: string[]
  customizedGreeting: string
  customizedCoverLetter: string
  updatedAt?: string
}

export interface JobApplicationItem {
  id: string
  userId: string
  resumeId?: string
  resumeName?: string
  jobId: string
  jobTitle: string
  company: string
  city: string
  salaryMin: number
  salaryMax: number
  stage: string
  applyChannel: string
  applyDate?: string
  hrContact?: string
  nextActionDate?: string
  notes?: string
  interviewRecords?: Array<{
    round_title: string
    interview_time: string
    interviewer?: string
    questions_and_feedback?: string
    result?: string
    recorded_at?: string
  }>
  offerDetails?: {
    salary?: string
    benefits?: string
    deadline?: string
    status?: string
  }
  createdAt?: string
  updatedAt?: string
}

export interface MockInterviewSessionItem {
  id: string
  targetRole: string
  roleType: string
  difficulty: string
  status: string
  overallScore: number
  feedbackSummary: string
  detailedDimensions?: {
    technical_depth?: number
    logic_structure?: number
    communication?: number
    star_framework?: number
    culture_fit?: number
  }
  roundsCount?: number
  records?: MockInterviewRecordItem[]
  createdAt?: string
}

export interface MockInterviewRecordItem {
  id: string
  roundNumber: number
  questionType: string
  question: string
  expectedKeyPoints?: string[]
  userAnswer?: string
  score: number
  feedback: string
  modelAnswer: string
  improvementTips?: string[]
  createdAt?: string
}

export const jobService = {
  // 简历管理
  async listResumes(): Promise<{ items: ResumeProfile[] }> {
    return apiClient.get('/jobs/resumes')
  },
  async getResume(id: string): Promise<ResumeProfile> {
    return apiClient.get(`/jobs/resumes/${id}`)
  },
  async parseResume(rawText: string): Promise<{ parsedData: any; score: number; scoreDetails: any }> {
    return apiClient.post('/jobs/resumes/parse', { raw_text: rawText })
  },
  async saveResume(data: { name: string; raw_text: string; parsed_data?: any; resume_id?: string; is_default?: boolean }): Promise<any> {
    return apiClient.post('/jobs/resumes', data)
  },
  async starPolish(resumeId: string, data: { project_name: string; tech_stack?: string[]; background?: string; target_jd?: string }): Promise<{ starOptimized: any }> {
    return apiClient.post(`/jobs/resumes/${resumeId}/star-polish`, data)
  },
  async createVersion(resumeId: string, data: { version_name: string; target_job_title: string; target_jd?: string; custom_data?: any }): Promise<any> {
    return apiClient.post(`/jobs/resumes/${resumeId}/versions`, data)
  },
  async deleteResume(resumeId: string): Promise<any> {
    return apiClient.delete(`/jobs/resumes/${resumeId}`)
  },

  // 岗位机会库
  async listPostings(params?: { keyword?: string; city?: string; job_type?: string; source_platform?: string; limit?: number; offset?: number }): Promise<{ items: JobOpportunity[]; total: number; offset: number; limit: number; hasMore: boolean }> {
    return apiClient.get('/jobs/postings', { params })
  },
  async getPosting(jobId: string): Promise<JobOpportunity> {
    return apiClient.get(`/jobs/postings/${jobId}`)
  },
  async createPosting(data: any): Promise<any> {
    return apiClient.post('/jobs/postings', data)
  },
  async parseJd(jdText: string, title?: string): Promise<{ parsedJd: any }> {
    return apiClient.post('/jobs/postings/parse-jd', { jd_text: jdText, title })
  },
  async getPlatforms(): Promise<{ platforms: Array<{ id: string; name: string; mode: string; icon: string; status: string }> }> {
    return apiClient.get('/jobs/postings/platforms')
  },
  async getCdpStatus(cdpUrl?: string): Promise<{ data: any }> {
    return apiClient.get('/jobs/postings/crawlers/cdp-status', { params: { cdp_url: cdpUrl } })
  },
  async syncJobs(data: { platform?: string; keyword?: string; city?: string; job_type?: string; limit_per_platform?: number; page?: number; max_pages?: number; enrich_details?: boolean; mode?: string; cdp_url?: string }): Promise<any> {
    return apiClient.post('/jobs/postings/sync', data)
  },
  async liveSearchJobs(data: { platform?: string; keyword?: string; city?: string; job_type?: string; limit_per_platform?: number; page?: number; max_pages?: number; mode?: string; cdp_url?: string }): Promise<{ code: number; message: string; data: { status: string; success?: boolean; jobs: JobOpportunity[]; total: number; page: number; has_more: boolean; next_page: number | null; persisted: false; platform_errors?: Record<string, { reason_code?: string; message?: string } | string> } }> {
    return apiClient.post('/jobs/postings/live-search', data)
  },

  // 人岗匹配
  async analyzeMatch(resumeId: string, jobId: string): Promise<JobMatchReport> {
    return apiClient.post('/jobs/matching/analyze', { resume_id: resumeId, job_id: jobId })
  },
  async generateGreeting(resumeId: string, jobId: string): Promise<{ greeting: string }> {
    return apiClient.post('/jobs/matching/greeting', { resume_id: resumeId, job_id: jobId })
  },

  // 投递看板
  async listApplications(stage?: string): Promise<{ items: JobApplicationItem[] }> {
    return apiClient.get('/jobs/applications', { params: { stage } })
  },
  async createApplication(data: { job_id: string; resume_id?: string; stage?: string; apply_channel?: string; notes?: string }): Promise<any> {
    return apiClient.post('/jobs/applications', data)
  },
  async updateApplicationStage(appId: string, data: { stage: string; notes?: string; next_action_date?: string }): Promise<any> {
    return apiClient.put(`/jobs/applications/${appId}/stage`, data)
  },
  async addInterviewRecord(appId: string, data: { round_title: string; interview_time: string; interviewer?: string; questions_and_feedback?: string; result?: string }): Promise<any> {
    return apiClient.post(`/jobs/applications/${appId}/interview`, data)
  },
  async updateOfferDetails(appId: string, offerDetails: any): Promise<any> {
    return apiClient.put(`/jobs/applications/${appId}/offer`, { offer_details: offerDetails })
  },
  async deleteApplication(appId: string): Promise<any> {
    return apiClient.delete(`/jobs/applications/${appId}`)
  },
  async getDashboardStats(): Promise<any> {
    return apiClient.get('/jobs/applications/dashboard/stats')
  },

  // 模拟面试
  async listInterviewSessions(): Promise<{ items: MockInterviewSessionItem[] }> {
    return apiClient.get('/jobs/interviews/sessions')
  },
  async getInterviewSession(sessionId: string): Promise<MockInterviewSessionItem> {
    return apiClient.get(`/jobs/interviews/sessions/${sessionId}`)
  },
  async createInterviewSession(data: { target_role?: string; role_type?: string; difficulty?: string; resume_id?: string; job_id?: string }): Promise<any> {
    return apiClient.post('/jobs/interviews/sessions', data)
  },
  async generateNextQuestion(sessionId: string, data?: { round_number?: number; question_type?: string }): Promise<MockInterviewRecordItem> {
    return apiClient.post(`/jobs/interviews/sessions/${sessionId}/next-question`, data || {})
  },
  async evaluateAnswer(recordId: string, userAnswer: string): Promise<MockInterviewRecordItem> {
    return apiClient.post(`/jobs/interviews/records/${recordId}/evaluate`, { user_answer: userAnswer })
  },
  async finishInterviewSession(sessionId: string): Promise<MockInterviewSessionItem> {
    return apiClient.post(`/jobs/interviews/sessions/${sessionId}/finish`)
  },

  // 网申自动填表
  async listMappings(): Promise<{ items: any[] }> {
    return apiClient.get('/jobs/autofill/mappings')
  },
  async generateAutoFillPayload(data: { resume_id: string; platform_name?: string; custom_overrides?: any }): Promise<any> {
    return apiClient.post('/jobs/autofill/payload', data)
  },
  async saveMapping(data: { platform_name: string; template_name: string; field_mappings: any; default_values: any }): Promise<any> {
    return apiClient.post('/jobs/autofill/mappings', data)
  }
}
