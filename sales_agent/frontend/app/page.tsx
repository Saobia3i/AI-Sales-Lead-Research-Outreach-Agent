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
  Accordion,
  AccordionSummary,
  AccordionDetails,
  ButtonGroup,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
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
  OpenInNew as OpenInNewIcon,
  ContentCopy as ContentCopyIcon,
  Phone as PhoneIcon,
  Mail as MailIcon,
  Settings as SettingsIcon,
  AutoAwesome as MagicIcon,
  ExpandMore as ExpandMoreIcon,
  Check as CheckIcon,
  FilterList as FilterIcon,
  Sms as SmsIcon,
  Call as CallIcon,
  Message as MessageIcon,
  FileDownload as DownloadIcon,
} from "@mui/icons-material";

type LeadBusiness = {
  business_name: string;
  category: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  google_maps_url: string | null;
  has_website: boolean;
  website_url: string | null;
  has_social_media: boolean;
  social_links: string[];
  source_url: string | null;
  confidence_no_website: number;
};

type LeadDraftEmail = {
  to_business: string;
  subject: string;
  body: string;
};

type LeadOutreachDrafts = {
  email_subject: string | null;
  email_body: string | null;
  social_dm_body: string | null;
  sms_whatsapp_body: string | null;
  call_script_body: string | null;
};

type LeadSearchResponse = {
  leads: LeadBusiness[];
  total_found: number;
  total_without_website: number;
  draft_email: LeadDraftEmail;
  search_query_used: string;
  errors: string[];
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#0ea5e9", // Sky blue
      contrastText: "#030712",
    },
    secondary: {
      main: "#10b981", // Emerald green
    },
    warning: {
      main: "#f59e0b", // Amber
    },
    error: {
      main: "#f43f5e", // Rose red
    },
    background: {
      default: "#030712", // Very dark grey/black
      paper: "#0b1528",   // Deep blue-grey
    },
    text: {
      primary: "#f3f4f6", // Off white
      secondary: "#9ca3af", // Cool grey
    },
  },
  typography: {
    fontFamily: '"Outfit", "Inter", "Roboto", "Helvetica", sans-serif',
    h4: {
      fontWeight: 800,
      letterSpacing: "-0.03em",
    },
    h5: {
      fontWeight: 700,
      letterSpacing: "-0.02em",
    },
    h6: {
      fontWeight: 600,
    },
    body1: {
      lineHeight: 1.6,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          textTransform: "none",
          fontWeight: 600,
          padding: "10px 20px",
          boxShadow: "none",
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            boxShadow: "0 0 15px rgba(14, 165, 233, 0.4)",
            transform: "translateY(-1px)",
          },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          backgroundColor: "rgba(15, 23, 42, 0.6)",
          transition: "all 0.2s ease-in-out",
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: "rgba(14, 165, 233, 0.5)",
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderColor: "#0ea5e9",
            boxShadow: "0 0 0 3px rgba(14, 165, 233, 0.2)",
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundImage: "none",
          backgroundColor: "#0d1b35",
          border: "1px solid rgba(255, 255, 255, 0.05)",
          boxShadow: "0 4px 30px rgba(0, 0, 0, 0.2)",
          transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        },
      },
    },
  },
});

const SUGGESTIONS = ["Beauty Salons", "Tutoring Centers", "Gyms", "Cafes", "Dentists", "Mechanics"];
const LOCATION_SUGGESTIONS = ["New York", "London", "Los Angeles", "Birmingham", "Chicago", "Manchester"];
const US_STATES = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", 
  "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", 
  "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", 
  "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", 
  "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", 
  "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", 
  "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", 
  "Wisconsin", "Wyoming"
];

export default function Home() {
  const [category, setCategory] = useState("Beauty Salons");
  const [location, setLocation] = useState("New York");
  const [senderName, setSenderName] = useState("");
  const [senderCompany, setSenderCompany] = useState("");
  const [serviceDesc, setServiceDesc] = useState(
    "We design stunning, high-converting websites optimized for local search and mobile, helping small businesses double their client bookings."
  );

  const [leads, setLeads] = useState<LeadBusiness[]>([]);
  const [globalEmail, setGlobalEmail] = useState<LeadDraftEmail | null>(null);
  const [selectedLead, setSelectedLead] = useState<LeadBusiness | null>(null);
  const [customOutreach, setCustomOutreach] = useState<LeadOutreachDrafts | null>(null);
  const [isCustomOutreachLoading, setIsCustomOutreachLoading] = useState(false);
  const [filterNoWebsite, setFilterNoWebsite] = useState(true);
  const [searchQueryUsed, setSearchQueryUsed] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Outreach Composer Tabs
  const [activeTab, setActiveTab] = useState<"email" | "social_dm" | "sms_whatsapp" | "call_script">("email");

  // Edited outreach channel states
  const [editedEmailSubject, setEditedEmailSubject] = useState("");
  const [editedEmailBody, setEditedEmailBody] = useState("");
  const [editedSocialDM, setEditedSocialDM] = useState("");
  const [editedSMS, setEditedSMS] = useState("");
  const [editedScript, setEditedScript] = useState("");

  // SMTP Gmail settings states
  const [smtpEmail, setSmtpEmail] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpServer, setSmtpServer] = useState("smtp.gmail.com");
  const [smtpPort, setSmtpPort] = useState(587);
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [emailSendStatus, setEmailSendStatus] = useState<{ success: boolean; message: string } | null>(null);

  // CSV Export Logic
  const exportToCSV = () => {
    if (displayedLeads.length === 0) return;
    
    // Define headers
    const headers = [
      "Business Name",
      "Category",
      "Address",
      "Phone",
      "Email",
      "Has Website",
      "Website URL",
      "Google Maps URL",
      "Social Links",
      "Source URL",
    ];
    
    // Map leads to rows
    const rows = displayedLeads.map((lead) => [
      lead.business_name,
      lead.category || "",
      lead.address || "",
      lead.phone || "",
      lead.email || "",
      lead.has_website ? "Yes" : "No",
      lead.website_url || "",
      lead.google_maps_url || "",
      (lead.social_links || []).join("; "),
      lead.source_url || "",
    ]);
    
    // Create CSV content
    const csvContent = [
      headers.join(","),
      ...rows.map((row) =>
        row
          .map((val) => {
            // Escape double quotes and wrap in quotes to handle commas/newlines
            const cleanVal = String(val).replace(/"/g, '""');
            return `"${cleanVal}"`;
          })
          .join(",")
      ),
    ].join("\n");
    
    // Download file
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `leads-${category.toLowerCase()}-${location.toLowerCase()}.csv`);
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // SMTP Email Send Logic
  const sendEmailViaSMTP = async () => {
    if (!selectedLead || !selectedLead.email) {
      alert("No email address found for this lead.");
      return;
    }
    if (!smtpEmail || !smtpPassword) {
      alert("Please configure your sender Gmail account and Gmail App Password first.");
      return;
    }
    
    setIsSendingEmail(true);
    setEmailSendStatus(null);
    
    try {
      const response = await fetch(`${apiBase}/api/v1/send_email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient_email: selectedLead.email,
          subject: editedEmailSubject,
          body: editedEmailBody,
          sender_email: smtpEmail,
          smtp_app_password: smtpPassword,
          smtp_server: smtpServer,
          smtp_port: smtpPort,
        }),
      });
      
      const data = await response.json();
      if (response.ok) {
        setEmailSendStatus({ success: true, message: "Email sent successfully!" });
      } else {
        throw new Error(data.detail || "Failed to send email");
      }
    } catch (err) {
      setEmailSendStatus({ success: false, message: err instanceof Error ? err.message : "Failed to send email" });
    } finally {
      setIsSendingEmail(false);
    }
  };

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setSelectedLead(null);
    setCustomOutreach(null);
    setLeads([]);

    try {
      const response = await fetch(`${apiBase}/api/v1/find_leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business_category: category,
          location: location,
          sender_name: senderName,
          sender_company: senderCompany,
          service_description: serviceDesc,
        }),
      });
      if (!response.ok) {
        throw new Error(`Lead search failed with status ${response.status}`);
      }
      const data = (await response.json()) as LeadSearchResponse;
      setLeads(data.leads);
      setGlobalEmail(data.draft_email);
      setSearchQueryUsed(data.search_query_used);
      if (data.errors && data.errors.length > 0) {
        setError(data.errors.join(", "));
      }

      // Default select the first lead if any exist
      if (data.leads && data.leads.length > 0) {
        const firstNoWeb = data.leads.find((l) => !l.has_website);
        if (firstNoWeb) {
          selectLead(firstNoWeb);
        } else {
          selectLead(data.leads[0]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }

  const selectLead = async (lead: LeadBusiness) => {
    setSelectedLead(lead);
    setCustomOutreach(null);
    setEditedEmailSubject("");
    setEditedEmailBody("");
    setEditedSocialDM("");
    setEditedSMS("");
    setEditedScript("");
    setIsCustomOutreachLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/v1/generate_lead_email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead: lead,
          sender_name: senderName,
          sender_company: senderCompany,
          service_description: serviceDesc,
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as LeadOutreachDrafts;
        setCustomOutreach(data);
        setEditedEmailSubject(data.email_subject || "");
        setEditedEmailBody(data.email_body || "");
        setEditedSocialDM(data.social_dm_body || "");
        setEditedSMS(data.sms_whatsapp_body || "");
        setEditedScript(data.call_script_body || "");

        // Set default active tab based on available channels
        if (lead.email) {
          setActiveTab("email");
        } else if (lead.has_social_media && lead.social_links.length > 0) {
          setActiveTab("social_dm");
        } else if (lead.phone) {
          setActiveTab("sms_whatsapp");
        } else {
          setActiveTab("email");
        }
      } else {
        throw new Error("Failed to generate custom outreach");
      }
    } catch (err) {
      // Fallback
      const fallbackSubject = `Website proposal for ${lead.business_name}`;
      const fallbackBody =
        globalEmail?.body.replace("Prospect Business", lead.business_name) ||
        `Hi,\n\nI noticed ${lead.business_name} does not have a website...`;
      
      const fallbackDrafts: LeadOutreachDrafts = {
        email_subject: fallbackSubject,
        email_body: fallbackBody,
        social_dm_body: `Hi ${lead.business_name} team,\n\nI noticed you have an active page here but no main website yet...`,
        sms_whatsapp_body: `Hi, this is ${senderName} from ${senderCompany}. I saw ${lead.business_name} online and wanted to ask if you'd be open to a website proposal?`,
        call_script_body: `Pitch: Hi, I'm calling from ${senderCompany} regarding setting up a website for ${lead.business_name}...`,
      };

      setCustomOutreach(fallbackDrafts);
      setEditedEmailSubject(fallbackDrafts.email_subject || "");
      setEditedEmailBody(fallbackDrafts.email_body || "");
      setEditedSocialDM(fallbackDrafts.social_dm_body || "");
      setEditedSMS(fallbackDrafts.sms_whatsapp_body || "");
      setEditedScript(fallbackDrafts.call_script_body || "");
      setActiveTab("email");
    } finally {
      setIsCustomOutreachLoading(false);
    }
  };

  const handleCopy = () => {
    let textToCopy = "";
    if (activeTab === "email") {
      textToCopy = `Subject: ${editedEmailSubject}\n\n${editedEmailBody}`;
    } else if (activeTab === "social_dm") {
      textToCopy = editedSocialDM;
    } else if (activeTab === "sms_whatsapp") {
      textToCopy = editedSMS;
    } else {
      textToCopy = editedScript;
    }

    if (textToCopy) {
      navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Clean phone number for WhatsApp direct linking
  const cleanPhoneForWa = (p: string) => {
    return p.replace(/\D/g, "");
  };

  // Filter leads based on toggle
  const displayedLeads = leads.filter((lead) => !filterNoWebsite || !lead.has_website);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: "100vh",
          bgcolor: "background.default",
          backgroundImage:
            "radial-gradient(ellipse at 50% -20%, rgba(14, 165, 233, 0.15), rgba(255, 255, 255, 0))",
          py: 4,
        }}
      >
        <Container maxWidth="xl">
          {/* Header Panel */}
          <Box sx={{ mb: 4, textAlign: "center" }}>
            <Typography
              variant="overline"
              color="primary.main"
              sx={{ fontWeight: 800, tracking: 2, display: "inline-block", mb: 1 }}
            >
              LINEARAI LEAD RESEARCHER
            </Typography>
            <Typography variant="h4" component="h1" sx={{ mb: 1, fontWeight: 900 }}>
              Find Offline Businesses & <span style={{ color: "#0ea5e9" }}>Contact Them Instantly</span>
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 700, mx: "auto" }}>
              Locate businesses without websites, extract emails, social pages, or phone numbers, and
              generate custom messages for WhatsApp, DMs, or phone scripts in one click.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {/* Left: Input Form Panel */}
            <Grid size={{ xs: 12, md: 4 }}>
              <Card sx={{ mb: 3 }}>
                <CardContent sx={{ p: 3 }}>
                  <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                    <SearchIcon color="primary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Search Parameters</Typography>
                  </Box>
                  <form onSubmit={runSearch}>
                    <Grid container spacing={2.5}>
                      <Grid size={12}>
                        <TextField
                          fullWidth
                          label="Business Category"
                          value={category}
                          onChange={(e) => setCategory(e.target.value)}
                          placeholder="e.g. Salons, Tutoring Centers, Bakeries"
                          required
                          variant="outlined"
                          size="small"
                        />
                        <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.8 }}>
                          {SUGGESTIONS.map((sug) => (
                            <Chip
                              key={sug}
                              label={sug}
                              size="small"
                              onClick={() => setCategory(sug)}
                              variant={category.toLowerCase() === sug.toLowerCase() ? "filled" : "outlined"}
                              color={category.toLowerCase() === sug.toLowerCase() ? "primary" : "default"}
                              sx={{ cursor: "pointer", fontSize: "0.75rem" }}
                            />
                          ))}
                        </Box>
                      </Grid>
                      <Grid size={12}>
                        <TextField
                          fullWidth
                          label="Location (City / Area)"
                          value={location}
                          onChange={(e) => setLocation(e.target.value)}
                          placeholder="e.g. New York, London, Los Angeles"
                          required
                          variant="outlined"
                          size="small"
                        />
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1 }}>
                          {LOCATION_SUGGESTIONS.map((loc) => (
                            <Chip
                              key={loc}
                              label={loc}
                              size="small"
                              onClick={() => setLocation(loc)}
                              variant={location.toLowerCase() === loc.toLowerCase() ? "filled" : "outlined"}
                              color={location.toLowerCase() === loc.toLowerCase() ? "primary" : "default"}
                              sx={{ cursor: "pointer", fontSize: "0.75rem" }}
                            />
                          ))}
                        </Box>
                        <FormControl fullWidth size="small" sx={{ mt: 1.5 }}>
                          <InputLabel id="us-state-label" sx={{ color: "rgba(255,255,255,0.7)" }}>Or Select US State Preset</InputLabel>
                          <Select
                            labelId="us-state-label"
                            value={US_STATES.includes(location.replace(", USA", "")) ? location.replace(", USA", "") : ""}
                            label="Or Select US State Preset"
                            onChange={(e) => {
                              if (e.target.value) {
                                setLocation(e.target.value + ", USA");
                              }
                            }}
                            sx={{
                              bgcolor: "rgba(15, 23, 42, 0.4)",
                              "& .MuiOutlinedInput-notchedOutline": {
                                borderColor: "rgba(255, 255, 255, 0.1)",
                              },
                              "&:hover .MuiOutlinedInput-notchedOutline": {
                                borderColor: "rgba(255, 255, 255, 0.2)",
                              },
                            }}
                          >
                            <MenuItem value=""><em>None (Custom location)</em></MenuItem>
                            {US_STATES.map((state) => (
                              <MenuItem key={state} value={state}>{state}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>

                      {/* Outreach Settings Collapsible */}
                      <Grid size={12}>
                        <Accordion
                          disableGutters
                          sx={{
                            bgcolor: "rgba(15, 23, 42, 0.4)",
                            border: "1px solid rgba(255, 255, 255, 0.05)",
                            borderRadius: "10px !important",
                            boxShadow: "none",
                            "&:before": { display: "none" },
                          }}
                        >
                          <AccordionSummary expandIcon={<ExpandMoreIcon color="primary" />}>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                              <SettingsIcon fontSize="small" color="primary" sx={{ mr: 1 }} />
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                Outreach Signature & Service Info
                              </Typography>
                            </Box>
                          </AccordionSummary>
                          <AccordionDetails sx={{ p: 2, pt: 0 }}>
                            <Grid container spacing={2}>
                              <Grid size={6}>
                                <TextField
                                  fullWidth
                                  label="Your Name"
                                  value={senderName}
                                  onChange={(e) => setSenderName(e.target.value)}
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid size={6}>
                                <TextField
                                  fullWidth
                                  label="Your Company"
                                  value={senderCompany}
                                  onChange={(e) => setSenderCompany(e.target.value)}
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid size={12}>
                                <TextField
                                  fullWidth
                                  multiline
                                  rows={3}
                                  label="Service Offer Description"
                                  value={serviceDesc}
                                  onChange={(e) => setServiceDesc(e.target.value)}
                                  placeholder="What value do you offer local businesses?"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                            </Grid>
                          </AccordionDetails>
                        </Accordion>
                      </Grid>
                      {/* SMTP Email Settings Collapsible */}
                      <Grid size={12} sx={{ mt: 1 }}>
                        <Accordion
                          disableGutters
                          sx={{
                            bgcolor: "rgba(15, 23, 42, 0.4)",
                            border: "1px solid rgba(255, 255, 255, 0.05)",
                            borderRadius: "10px !important",
                            boxShadow: "none",
                            "&:before": { display: "none" },
                          }}
                        >
                          <AccordionSummary expandIcon={<ExpandMoreIcon color="secondary" />}>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                              <EmailIcon fontSize="small" color="secondary" sx={{ mr: 1 }} />
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                Email SMTP Settings (Gmail)
                              </Typography>
                            </Box>
                          </AccordionSummary>
                          <AccordionDetails sx={{ p: 2, pt: 0 }}>
                            <Grid container spacing={2}>
                              <Grid size={12}>
                                <TextField
                                  fullWidth
                                  label="Sender Gmail Account"
                                  value={smtpEmail}
                                  onChange={(e) => setSmtpEmail(e.target.value)}
                                  placeholder="yourname@gmail.com"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid size={12}>
                                <TextField
                                  fullWidth
                                  type="password"
                                  label="Gmail App Password"
                                  value={smtpPassword}
                                  onChange={(e) => setSmtpPassword(e.target.value)}
                                  placeholder="16-character app password"
                                  variant="outlined"
                                  size="small"
                                  helperText="Use a Google App Password (not your main password)"
                                />
                              </Grid>
                              <Grid size={8}>
                                <TextField
                                  fullWidth
                                  label="SMTP Server"
                                  value={smtpServer}
                                  onChange={(e) => setSmtpServer(e.target.value)}
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid size={4}>
                                <TextField
                                  fullWidth
                                  type="number"
                                  label="Port"
                                  value={smtpPort}
                                  onChange={(e) => setSmtpPort(Number(e.target.value))}
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                            </Grid>
                          </AccordionDetails>
                        </Accordion>
                      </Grid>

                      <Grid size={12}>
                        <Button
                          fullWidth
                          type="submit"
                          variant="contained"
                          color="primary"
                          disabled={isLoading}
                          startIcon={isLoading ? <CircularProgress size={20} color="inherit" /> : <SearchIcon />}
                          sx={{ height: 46 }}
                        >
                          {isLoading ? "Scraping & Researching..." : "Scan & Discover Leads"}
                        </Button>
                      </Grid>
                    </Grid>
                  </form>
                </CardContent>
              </Card>

              {/* Stats Panel */}
              {leads.length > 0 && (
                <Card sx={{ borderLeft: 4, borderLeftColor: "primary.main" }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5, fontWeight: 700 }}>
                      DISCOVERY METRICS
                    </Typography>
                    <Grid container spacing={2}>
                      <Grid size={6} sx={{ textAlign: "center" }}>
                        <Typography variant="h5" color="text.primary" sx={{ fontWeight: 800 }}>
                          {leads.length}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Total Identified
                        </Typography>
                      </Grid>
                      <Grid size={6} sx={{ textAlign: "center" }}>
                        <Typography variant="h5" color="error.main" sx={{ fontWeight: 800 }}>
                          {leads.filter((l) => !l.has_website).length}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          No Standalone Site
                        </Typography>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              )}
            </Grid>

            {/* Middle: Discovered Leads Table/List */}
            <Grid size={{ xs: 12, md: 5 }}>
              <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                <CardContent sx={{ p: 3, flexGrow: 1, display: "flex", flexDirection: "column", minHeight: 400 }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      mb: 2,
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center" }}>
                      <BusinessIcon color="primary" sx={{ mr: 1 }} />
                      <Typography variant="h6">Discovered Leads</Typography>
                    </Box>

                    {leads.length > 0 && (
                      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                        <Button
                          variant="outlined"
                          color="secondary"
                          size="small"
                          onClick={exportToCSV}
                          startIcon={<DownloadIcon sx={{ fontSize: "14px !important" }} />}
                          sx={{
                            height: 24,
                            fontSize: "0.75rem",
                            borderRadius: "16px",
                            px: 1.5,
                            borderWidth: 1,
                            borderColor: "secondary.main",
                            color: "secondary.main",
                            "&:hover": {
                              borderWidth: 1,
                              bgcolor: "rgba(16, 185, 129, 0.08)",
                            }
                          }}
                        >
                          Export CSV
                        </Button>
                        <Chip
                          icon={<FilterIcon sx={{ fontSize: "14px !important" }} />}
                          label="No Website Only"
                          onClick={() => setFilterNoWebsite(!filterNoWebsite)}
                          color={filterNoWebsite ? "primary" : "default"}
                          variant={filterNoWebsite ? "filled" : "outlined"}
                          size="small"
                          sx={{ cursor: "pointer" }}
                        />
                      </Box>
                    )}
                  </Box>
                  <Divider sx={{ mb: 2, borderColor: "rgba(255,255,255,0.06)" }} />

                  {isLoading ? (
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        flexGrow: 1,
                        py: 8,
                      }}
                    >
                      <CircularProgress size={45} sx={{ mb: 2 }} />
                      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                        Scraping local directory data & business phone lines...
                      </Typography>
                      <Typography variant="caption" color="primary.main" sx={{ mt: 0.5 }}>
                        Analyzing domains & checking server response headers
                      </Typography>
                    </Box>
                  ) : leads.length === 0 ? (
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        flexGrow: 1,
                        py: 8,
                        textAlign: "center",
                      }}
                    >
                      <HelpIcon sx={{ fontSize: 48, color: "rgba(255,255,255,0.1)", mb: 1.5 }} />
                      <Typography variant="body2" color="text.secondary">
                        Enter details on the left and scan to start researching.
                      </Typography>
                    </Box>
                  ) : displayedLeads.length === 0 ? (
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        flexGrow: 1,
                        py: 8,
                        textAlign: "center",
                      }}
                    >
                      <CheckCircleIcon color="success" sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">
                        Awesome! All found businesses have an active standalone website.
                      </Typography>
                    </Box>
                  ) : (
                    <List sx={{ overflowY: "auto", maxHeight: 650, flexGrow: 1, pr: 1 }} disablePadding>
                      {displayedLeads.map((lead, idx) => {
                        const isSelected = selectedLead?.business_name === lead.business_name;
                        return (
                          <Paper
                            key={idx}
                            variant="outlined"
                            onClick={() => selectLead(lead)}
                            sx={{
                              p: 2,
                              mb: 1.8,
                              cursor: "pointer",
                              borderRadius: 3,
                              borderColor: isSelected
                                ? "primary.main"
                                : "rgba(255, 255, 255, 0.05)",
                              bgcolor: isSelected
                                ? "rgba(14, 165, 233, 0.08)"
                                : "rgba(11, 21, 40, 0.4)",
                              transition: "all 0.2s ease-in-out",
                              "&:hover": {
                                borderColor: isSelected ? "primary.main" : "rgba(255, 255, 255, 0.15)",
                                bgcolor: isSelected
                                  ? "rgba(14, 165, 233, 0.12)"
                                  : "rgba(15, 23, 42, 0.8)",
                              },
                            }}
                          >
                            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, pr: 1 }}>
                                {lead.business_name}
                              </Typography>
                              <Box>
                                {lead.has_website ? (
                                  <Chip
                                    label="Has Website"
                                    color="success"
                                    size="small"
                                    sx={{ height: 20, fontSize: "0.65rem", fontWeight: "bold" }}
                                  />
                                ) : lead.has_social_media ? (
                                  <Chip
                                    label="Social Page Only"
                                    color="warning"
                                    size="small"
                                    sx={{ height: 20, fontSize: "0.65rem", fontWeight: "bold" }}
                                  />
                                ) : (
                                  <Chip
                                    label="No Website"
                                    color="error"
                                    size="small"
                                    sx={{ height: 20, fontSize: "0.65rem", fontWeight: "bold" }}
                                  />
                                )}
                              </Box>
                            </Box>

                            <Grid container spacing={1} sx={{ mt: 0.5 }}>
                              {lead.address && (
                                <Grid size={12} sx={{ display: "flex", alignItems: "center" }}>
                                  <PlaceIcon sx={{ fontSize: 14, mr: 0.8, color: "text.secondary" }} />
                                  <Typography variant="caption" color="text.secondary">
                                    {lead.address}
                                  </Typography>
                                </Grid>
                              )}
                              {lead.phone && (
                                <Grid size={6} sx={{ display: "flex", alignItems: "center" }}>
                                  <PhoneIcon sx={{ fontSize: 14, mr: 0.8, color: "text.secondary" }} />
                                  <Typography variant="caption" color="text.secondary">
                                    {lead.phone}
                                  </Typography>
                                </Grid>
                              )}
                              {lead.email && (
                                <Grid size={6} sx={{ display: "flex", alignItems: "center" }}>
                                  <MailIcon sx={{ fontSize: 14, mr: 0.8, color: "text.secondary" }} />
                                  <Typography variant="caption" color="text.secondary">
                                    {lead.email}
                                  </Typography>
                                </Grid>
                              )}
                            </Grid>

                            {/* Direct Call / Contact Actions */}
                            <Box sx={{ mt: 1.5, display: "flex", flexWrap: "wrap", gap: 0.8 }}>
                              {lead.google_maps_url && (
                                <Button
                                  href={lead.google_maps_url}
                                  target="_blank"
                                  size="small"
                                  variant="text"
                                  color="primary"
                                  startIcon={<OpenInNewIcon sx={{ fontSize: 12 }} />}
                                  sx={{ p: 0, minWidth: 0, height: "auto", fontSize: "0.7rem", mr: 2 }}
                                >
                                  Maps
                                </Button>
                              )}

                              {lead.phone && (
                                <>
                                  <Button
                                    href={`tel:${lead.phone}`}
                                    size="small"
                                    variant="outlined"
                                    color="primary"
                                    startIcon={<CallIcon sx={{ fontSize: 12 }} />}
                                    sx={{ height: 24, fontSize: "0.68rem", px: 1 }}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    Call
                                  </Button>

                                  <Button
                                    href={`https://wa.me/${cleanPhoneForWa(lead.phone)}?text=${encodeURIComponent(
                                      // Use draft from the currently-selected lead if available,
                                      // otherwise build a quick generic message so the link is never empty.
                                      (selectedLead?.business_name === lead.business_name && editedSMS)
                                        ? editedSMS
                                        : `Hi, I came across ${lead.business_name} and wanted to reach out about building a professional website for your business. Would you be open to a quick chat?`
                                    )}`}
                                    target="_blank"
                                    size="small"
                                    variant="outlined"
                                    color="secondary"
                                    startIcon={<MessageIcon sx={{ fontSize: 12 }} />}
                                    sx={{ height: 24, fontSize: "0.68rem", px: 1 }}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    WhatsApp
                                  </Button>
                                </>
                              )}

                              {lead.social_links && lead.social_links.length > 0 && (
                                <Button
                                  href={lead.social_links[0]}
                                  target="_blank"
                                  size="small"
                                  variant="outlined"
                                  color="warning"
                                  startIcon={<LanguageIcon sx={{ fontSize: 12 }} />}
                                  sx={{ height: 24, fontSize: "0.68rem", px: 1 }}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  Social Page
                                </Button>
                              )}
                            </Box>
                          </Paper>
                        );
                      })}
                    </List>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Right: AI Outreach Editor (Multi-channel) */}
            <Grid size={{ xs: 12, md: 3 }}>
              <Card sx={{ height: "100%", borderLeft: 5, borderLeftColor: "primary.main" }}>
                <CardContent sx={{ p: 3, display: "flex", flexDirection: "column", height: "100%" }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      mb: 1.5,
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center" }}>
                      <EmailIcon color="primary" sx={{ mr: 1 }} />
                      <Typography variant="h6">Outreach Pitch</Typography>
                    </Box>

                    {customOutreach && !isCustomOutreachLoading && (
                      <Tooltip title={copied ? "Copied!" : "Copy to Clipboard"}>
                        <IconButton onClick={handleCopy} color="primary" size="small">
                          {copied ? <CheckIcon /> : <ContentCopyIcon />}
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>

                  {/* Channel Tab selector */}
                  {selectedLead && (
                    <Box sx={{ mb: 2 }}>
                      <ButtonGroup size="small" fullWidth color="primary" variant="outlined">
                        <Button
                          onClick={() => setActiveTab("email")}
                          variant={activeTab === "email" ? "contained" : "outlined"}
                          sx={{ fontSize: "0.75rem", p: "4px 8px" }}
                          disabled={!selectedLead.email && !customOutreach?.email_body}
                        >
                          Email
                        </Button>
                        <Button
                          onClick={() => setActiveTab("social_dm")}
                          variant={activeTab === "social_dm" ? "contained" : "outlined"}
                          sx={{ fontSize: "0.75rem", p: "4px 8px" }}
                          disabled={!selectedLead.has_social_media && !customOutreach?.social_dm_body}
                        >
                          DM
                        </Button>
                        <Button
                          onClick={() => setActiveTab("sms_whatsapp")}
                          variant={activeTab === "sms_whatsapp" ? "contained" : "outlined"}
                          sx={{ fontSize: "0.75rem", p: "4px 8px" }}
                          disabled={!selectedLead.phone && !customOutreach?.sms_whatsapp_body}
                        >
                          WhatsApp
                        </Button>
                        <Button
                          onClick={() => setActiveTab("call_script")}
                          variant={activeTab === "call_script" ? "contained" : "outlined"}
                          sx={{ fontSize: "0.75rem", p: "4px 8px" }}
                          disabled={!selectedLead.phone && !customOutreach?.call_script_body}
                        >
                          Call Script
                        </Button>
                      </ButtonGroup>
                    </Box>
                  )}

                  <Divider sx={{ mb: 2, borderColor: "rgba(255,255,255,0.06)" }} />

                  {isCustomOutreachLoading ? (
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        flexGrow: 1,
                        py: 8,
                      }}
                    >
                      <CircularProgress size={35} sx={{ mb: 2 }} />
                      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                        Generating personalized pitches for all contact channels...
                      </Typography>
                    </Box>
                  ) : !selectedLead ? (
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        flexGrow: 1,
                        py: 8,
                        textAlign: "center",
                      }}
                    >
                      <MagicIcon sx={{ fontSize: 40, color: "rgba(255,255,255,0.1)", mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">
                        Select a lead to review custom outreach drafts.
                      </Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <Typography variant="caption" color="text.secondary">
                        COMPOSED FOR: <strong>{selectedLead.business_name}</strong>
                      </Typography>

                      {activeTab === "email" && (
                        <TextField
                          fullWidth
                          label="Email Subject"
                          value={editedEmailSubject}
                          onChange={(e) => setEditedEmailSubject(e.target.value)}
                          variant="outlined"
                          size="small"
                        />
                      )}

                      <TextField
                        fullWidth
                        multiline
                        rows={14}
                        label={
                          activeTab === "email"
                            ? "Email Body"
                            : activeTab === "social_dm"
                            ? "Social Direct Message"
                            : activeTab === "sms_whatsapp"
                            ? "WhatsApp/SMS Text"
                            : "Phone Pitch Script"
                        }
                        value={
                          activeTab === "email"
                            ? editedEmailBody
                            : activeTab === "social_dm"
                            ? editedSocialDM
                            : activeTab === "sms_whatsapp"
                            ? editedSMS
                            : editedScript
                        }
                        onChange={(e) => {
                          if (activeTab === "email") setEditedEmailBody(e.target.value);
                          else if (activeTab === "social_dm") setEditedSocialDM(e.target.value);
                          else if (activeTab === "sms_whatsapp") setEditedSMS(e.target.value);
                          else setEditedScript(e.target.value);
                        }}
                        variant="outlined"
                        sx={{
                          "& .MuiOutlinedInput-root": {
                            fontFamily: "monospace",
                            fontSize: "0.85rem",
                            lineHeight: 1.5,
                          },
                        }}
                      />

                      <Button
                        fullWidth
                        variant="contained"
                        color="primary"
                        onClick={handleCopy}
                        startIcon={copied ? <CheckIcon /> : <ContentCopyIcon />}
                      >
                        {copied
                          ? "Copied to Clipboard!"
                          : activeTab === "email"
                          ? "Copy Subject & Body"
                          : "Copy Pitch"}
                      </Button>

                      {activeTab === "email" && selectedLead && selectedLead.email && (
                        <>
                          <Button
                            fullWidth
                            variant="contained"
                            color="success"
                            disabled={isSendingEmail}
                            onClick={sendEmailViaSMTP}
                            startIcon={isSendingEmail ? <CircularProgress size={20} color="inherit" /> : <EmailIcon />}
                            sx={{
                              mt: 1,
                              height: 40,
                              fontWeight: 700,
                              bgcolor: "#10b981",
                              "&:hover": {
                                bgcolor: "#059669",
                                boxShadow: "0 0 15px rgba(16, 185, 129, 0.4)",
                              }
                            }}
                          >
                            {isSendingEmail ? "Sending Email..." : `Send Email to ${selectedLead.email}`}
                          </Button>
                          {emailSendStatus && (
                            <Alert
                              severity={emailSendStatus.success ? "success" : "error"}
                              sx={{
                                mt: 1,
                                borderRadius: 2,
                                bgcolor: emailSendStatus.success ? "rgba(16, 185, 129, 0.1)" : "rgba(244, 63, 94, 0.1)",
                                border: emailSendStatus.success ? "1px solid rgba(16, 185, 129, 0.2)" : "1px solid rgba(244, 63, 94, 0.2)",
                              }}
                            >
                              {emailSendStatus.message}
                            </Alert>
                          )}
                        </>
                      )}
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
