import React from "react";
import ReactDOM from "react-dom/client";
import {BrowserRouter} from "react-router-dom";
import App from "./App";
import {AuthProvider} from "./context/AuthContext";
import "./styles.css";
import "./inspection_styles.css";
import "./outlets_styles.css";
import "./employee_styles.css";
import "./attendance_styles.css";
import "./workforce_controls_styles.css";
import "./mobile_workspace.css";

import "./notification_mobile.css";

ReactDOM.createRoot(document.getElementById("root")).render(<React.StrictMode><BrowserRouter><AuthProvider><App/></AuthProvider></BrowserRouter></React.StrictMode>);
// date-display-ddmmyyyy-v1
