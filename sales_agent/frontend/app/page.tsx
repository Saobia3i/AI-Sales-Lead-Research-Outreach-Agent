"use client";

import { FormEvent, useState } from "react";
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  Container,
  Box,
  Typography,
  TextField,
  Button,
  Card,
  CardContent,
  Alert,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Chip,
  CircularProgress,
  Paper,
  IconButton,
  Tooltip,
} from "@mui/material";
import Grid from "@mui/material/Grid";
import {
  Search as SearchIcon,
  Email as EmailIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  HelpOutlined as HelpIcon,
  Business as BusinessIcon,
  Language as LanguageIcon,
  Place as PlaceIcon,
  People as PeopleIcon,
  OpenInNew as OpenInNewIcon,
  ContentCopy as ContentCopyIcon,
  Article as ArticleIcon,
} from "@mui/icons-material";

type EvidenceRef = {
  url: string;
  relevance_score: number;
  used_for_claim: string;
};

type CompanyProfile = {
  company_name: string;
  website: string | null;
  industry: string | null;
  company_size_estimate: string | null;
  hq_location: string | null;
  recent_news: { headline: string; summary: string; source_url: string; date: string | null }[];
  pain_point_signals: string[];
  evidence_sources: EvidenceRef[];
  insufficient_evidence: string[];
};

type FullPipelineResponse = {
  profile: CompanyProfile;
  draft_email: { subject: string; body: string; claims_used: string[] };
  verification_report: {
    claim: string;
    status: "verified" | "unverified" | "not_a_factual_claim";
    evidence_ref: string | null;
    confidence: number;
  }[];
  errors: string[];
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Design Palette
const theme = createTheme({
  palette: {
    primary: {
      main: "#2f6654", // Moss green
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#c8513d", // Coral
    },
    background: {
      default: "#f7f8f5", // Light neutral paper tone
      paper: "#ffffff",
    },
    text: {
      primary: "#17211f", // Dark Ink
      secondary: "#5c6b68",
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 700,
      letterSpacing: "-0.02em",
    },
    h6: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          textTransform: "none",
          fontWeight: 600,
          boxShadow: "none",
          "&:hover": {
            boxShadow: "none",
          },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05), 0 20px 25px -5px rgba(0, 0, 0, 0.05)",
          border: "1px solid #e2e8f0",
        },
      },
    },
  },
});

export default function Home() {
  const [companyInput, setCompanyInput] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [result, setResult] = useState<FullPipelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  async function runPipeline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${apiBase}/api/v1/full_pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_input: companyInput, product_description: productDescription }),
      });
      if (!response.ok) {
        throw new Error(`Pipeline failed with ${response.status}`);
      }
      setResult((await response.json()) as FullPipelineResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }

  const handleCopy = () => {
    if (result) {
      navigator.clipboard.writeText(
        `Subject: ${result.draft_email.subject}\n\n${result.draft_email.body}`
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        
        {/* Header Hero Section */}
        <Box sx={{ bgcolor: "background.paper", borderBottom: 1, borderColor: "divider", py: 5 }}>
          <Container maxWidth="lg">
            <Grid container spacing={4} sx={{ alignItems: "center" }}>
              <Grid size={{ xs: 12, md: 5 }}>
                <Typography variant="overline" color="primary" sx={{ fontWeight: "bold", tracking: 1.5 }}>
                  LINEARAI SERVICE LINE
                </Typography>
                <Typography variant="h4" component="h1" sx={{ mt: 1, mb: 2, color: "text.primary" }}>
                  Sales Lead Research Agent
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                  Research a prospect company, generate real-time web evidence profiles, and draft highly personalized cold emails verified for factual claims.
                </Typography>
              </Grid>
              
              {/* Form Card */}
              <Grid size={{ xs: 12, md: 7 }}>
                <Paper variant="outlined" sx={{ p: 3, borderRadius: 3, bgcolor: "background.paper" }}>
                  <form onSubmit={runPipeline}>
                    <Grid container spacing={3}>
                      <Grid size={12}>
                        <TextField
                          fullWidth
                          label="Company Name or Website"
                          value={companyInput}
                          onChange={(e) => setCompanyInput(e.target.value)}
                          placeholder="e.g. OpenAI or openai.com"
                          required
                          variant="outlined"
                          size="small"
                        />
                      </Grid>
                      <Grid size={12}>
                        <TextField
                          fullWidth
                          multiline
                          rows={3}
                          label="Product or Value Proposition"
                          value={productDescription}
                          onChange={(e) => setProductDescription(e.target.value)}
                          placeholder="e.g. We build custom agentic AI systems for sales and operations teams."
                          required
                          variant="outlined"
                        />
                      </Grid>
                      <Grid size={12}>
                        <Button
                          fullWidth
                          type="submit"
                          variant="contained"
                          color="primary"
                          disabled={isLoading}
                          startIcon={isLoading ? <CircularProgress size={20} color="inherit" /> : <SearchIcon />}
                          sx={{ height: 44 }}
                        >
                          {isLoading ? "Running Research Pipeline..." : "Run Research & Outreach"}
                        </Button>
                      </Grid>
                    </Grid>
                  </form>
                </Paper>
              </Grid>
            </Grid>
          </Container>
        </Box>

        {/* Results / Feedback Section */}
        <Container maxWidth="lg" sx={{ py: 4 }}>
          {error && (
            <Alert severity="error" variant="outlined" sx={{ mb: 4, borderRadius: 2 }}>
              {error}
            </Alert>
          )}

          {result && (
            <Grid container spacing={3}>
              
              {/* Left Column: Company Profile & news */}
              <Grid size={{ xs: 12, md: 6 }}>
                <Grid container spacing={3}>
                  
                  {/* Profile Metadata */}
                  <Grid size={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                          <BusinessIcon color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Company Profile</Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={2}>
                          <Grid size={12} sx={{ display: "flex", alignItems: "center" }}>
                            <Typography sx={{ fontWeight: 600, minWidth: 100 }} variant="body2" color="text.secondary">Name:</Typography>
                            <Typography variant="body2">{result.profile.company_name}</Typography>
                          </Grid>
                          <Grid size={12} sx={{ display: "flex", alignItems: "center" }}>
                            <Typography sx={{ fontWeight: 600, minWidth: 100 }} variant="body2" color="text.secondary">Website:</Typography>
                            {result.profile.website ? (
                              <Button
                                href={result.profile.website}
                                target="_blank"
                                size="small"
                                variant="text"
                                color="primary"
                                startIcon={<LanguageIcon fontSize="small" />}
                                endIcon={<OpenInNewIcon fontSize="small" />}
                                sx={{ p: 0, textTransform: "none", minWidth: 0 }}
                              >
                                {result.profile.website.replace("https://", "").replace("http://", "")}
                              </Button>
                            ) : (
                              <Typography variant="body2" color="text.secondary">No data found</Typography>
                            )}
                          </Grid>
                          <Grid size={12} sx={{ display: "flex", alignItems: "center" }}>
                            <Typography sx={{ fontWeight: 600, minWidth: 100 }} variant="body2" color="text.secondary">HQ Location:</Typography>
                            <Typography variant="body2" sx={{ display: "flex", alignItems: "center" }}>
                              <PlaceIcon sx={{ fontSize: 16, mr: 0.5, color: "text.secondary" }} />
                              {result.profile.hq_location ?? "No data found"}
                            </Typography>
                          </Grid>
                          <Grid size={12} sx={{ display: "flex", alignItems: "center" }}>
                            <Typography sx={{ fontWeight: 600, minWidth: 100 }} variant="body2" color="text.secondary">Size Est.:</Typography>
                            <Typography variant="body2" sx={{ display: "flex", alignItems: "center" }}>
                              <PeopleIcon sx={{ fontSize: 16, mr: 0.5, color: "text.secondary" }} />
                              {result.profile.company_size_estimate ?? "No data found"}
                            </Typography>
                          </Grid>
                        </Grid>

                        {result.profile.insufficient_evidence.length > 0 && (
                          <Box sx={{ mt: 3, p: 1.5, borderRadius: 2, bgcolor: "#fff3f1", border: "1px solid #ffe3df" }}>
                            <Typography variant="caption" color="secondary.main" sx={{ display: "block", fontWeight: 600 }}>
                              Missing Web Evidence for: {result.profile.insufficient_evidence.join(", ")}
                            </Typography>
                          </Box>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Recent News */}
                  <Grid size={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                          <ArticleIcon color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Recent News</Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        {result.profile.recent_news.length > 0 ? (
                          <List disablePadding>
                            {result.profile.recent_news.map((item, idx) => (
                              <Box key={idx} sx={{ mb: idx !== result.profile.recent_news.length - 1 ? 2 : 0 }}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                                  {item.headline}
                                </Typography>
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontSize: "0.85rem" }}>
                                  {item.summary}
                                </Typography>
                                <Button
                                  href={item.source_url}
                                  target="_blank"
                                  size="small"
                                  color="primary"
                                  endIcon={<OpenInNewIcon sx={{ fontSize: 12 }} />}
                                  sx={{ p: 0, textTransform: "none", fontSize: "0.75rem" }}
                                >
                                  View Article Source
                                </Button>
                                {idx !== result.profile.recent_news.length - 1 && <Divider sx={{ mt: 2 }} />}
                              </Box>
                            ))}
                          </List>
                        ) : (
                          <Typography variant="body2" color="text.secondary">No news found in last 6 months</Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>

              {/* Right Column: Verified Outreach Email & Verification Pass */}
              <Grid size={{ xs: 12, md: 6 }}>
                <Grid container spacing={3}>

                  {/* Outreach Email Draft */}
                  <Grid size={12}>
                    <Card variant="outlined" sx={{ borderLeft: 5, borderLeftColor: "primary.main" }}>
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center" }}>
                            <EmailIcon color="primary" sx={{ mr: 1 }} />
                            <Typography variant="h6">Verified Outreach Draft</Typography>
                          </Box>
                          <Tooltip title={copied ? "Copied!" : "Copy to Clipboard"}>
                            <IconButton onClick={handleCopy} color="primary" size="small">
                              <ContentCopyIcon />
                            </IconButton>
                          </Tooltip>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        
                        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                          Subject: {result.draft_email.subject}
                        </Typography>
                        <Paper
                          variant="outlined"
                          sx={{
                            p: 2,
                            borderRadius: 2,
                            bgcolor: "background.default",
                            whiteSpace: "pre-wrap",
                            fontFamily: "monospace",
                            fontSize: "0.875rem",
                            lineHeight: 1.6,
                            color: "text.primary"
                          }}
                        >
                          {result.draft_email.body}
                        </Paper>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Verification Report */}
                  <Grid size={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                          <CheckCircleIcon color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Claims Verification Report</Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        {result.verification_report.length > 0 ? (
                          <List disablePadding>
                            {result.verification_report.map((item, idx) => (
                              <ListItem key={idx} disableGutters sx={{ alignItems: "flex-start", flexDirection: "column", mb: 2 }}>
                                <Box sx={{ display: "flex", alignItems: "center", width: "100%", mb: 1 }}>
                                  {item.status === "verified" ? (
                                    <Chip
                                      icon={<CheckCircleIcon sx={{ fontSize: "14px !important" }} />}
                                      label="VERIFIED"
                                      color="success"
                                      size="small"
                                      sx={{ fontWeight: "bold", height: 20 }}
                                    />
                                  ) : item.status === "unverified" ? (
                                    <Chip
                                      icon={<WarningIcon sx={{ fontSize: "14px !important" }} />}
                                      label="UNVERIFIED"
                                      color="error"
                                      size="small"
                                      sx={{ fontWeight: "bold", height: 20 }}
                                    />
                                  ) : (
                                    <Chip
                                      icon={<HelpIcon sx={{ fontSize: "14px !important" }} />}
                                      label="NON-FACTUAL CLAIM"
                                      color="default"
                                      size="small"
                                      sx={{ fontWeight: "bold", height: 20 }}
                                    />
                                  )}
                                  <Typography variant="caption" sx={{ ml: 1, color: "text.secondary", fontWeight: 500 }}>
                                    Confidence: {Math.round(item.confidence * 100)}%
                                  </Typography>
                                </Box>
                                <Typography variant="body2" sx={{ fontWeight: 500, mb: 0.5 }}>
                                  "{item.claim}"
                                </Typography>
                                {item.evidence_ref && (
                                  <Button
                                    href={item.evidence_ref}
                                    target="_blank"
                                    size="small"
                                    endIcon={<OpenInNewIcon sx={{ fontSize: 10 }} />}
                                    sx={{ p: 0, textTransform: "none", fontSize: "0.75rem", minHeight: 0, mt: 0.5 }}
                                  >
                                    Evidence: {item.evidence_ref.slice(0, 50)}...
                                  </Button>
                                )}
                              </ListItem>
                            ))}
                          </List>
                        ) : (
                          <Typography variant="body2" color="text.secondary">No factual claims found in email draft</Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>

              {/* Lower Section: Pain Points & Full Evidence List */}
              <Grid size={12}>
                <Grid container spacing={3}>
                  
                  {/* Pain Signals */}
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                          <WarningIcon color="warning" sx={{ mr: 1 }} />
                          <Typography variant="h6">Retrieved Pain Signals</Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        {result.profile.pain_point_signals.length > 0 ? (
                          <List>
                            {result.profile.pain_point_signals.map((signal, idx) => (
                              <ListItem key={idx} disableGutters>
                                <ListItemIcon sx={{ minWidth: 32 }}>
                                  <Chip label={idx + 1} size="small" variant="outlined" color="primary" sx={{ height: 20, width: 20, p: 0, "& .MuiChip-label": { p: 0 } }} />
                                </ListItemIcon>
                                <ListItemText primary={<Typography variant="body2">{signal}</Typography>} />
                              </ListItem>
                            ))}
                          </List>
                        ) : (
                          <Typography variant="body2" color="text.secondary">No signals found</Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* All Evidence Sources */}
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                          <LanguageIcon color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Evidence Source Registry</Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        {result.profile.evidence_sources.length > 0 ? (
                          <List disablePadding>
                            {result.profile.evidence_sources.map((source, idx) => (
                              <ListItem key={idx} disableGutters sx={{ py: 1, borderBottom: idx !== result.profile.evidence_sources.length - 1 ? "1px solid #e2e8f0" : "none" }}>
                                <Box sx={{ width: "100%" }}>
                                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                                    <Chip
                                      label={`Relevance: ${Math.round(source.relevance_score * 100)}%`}
                                      size="small"
                                      color={source.relevance_score >= 0.6 ? "primary" : "default"}
                                      variant="outlined"
                                      sx={{ height: 18, fontSize: "0.7rem", fontWeight: "bold" }}
                                    />
                                    <Button
                                      href={source.url}
                                      target="_blank"
                                      size="small"
                                      endIcon={<OpenInNewIcon sx={{ fontSize: 10 }} />}
                                      sx={{ p: 0, textTransform: "none", fontSize: "0.75rem", minWidth: 0 }}
                                    >
                                      Go to Source URL
                                    </Button>
                                  </Box>
                                  <Typography variant="body2" sx={{ color: "text.secondary", fontSize: "0.8rem", mt: 0.5 }}>
                                    {source.used_for_claim}
                                  </Typography>
                                </Box>
                              </ListItem>
                            ))}
                          </List>
                        ) : (
                          <Typography variant="body2" color="text.secondary">No evidence sources registered</Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                </Grid>
              </Grid>

            </Grid>
          )}
        </Container>
      </Box>
    </ThemeProvider>
  );
}
