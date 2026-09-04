using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography.X509Certificates;
using System.Threading.Tasks;
using UnityEngine;

using Opc.Ua;
using Opc.Ua.Client;

public class OpcUaClient : MonoBehaviour
{
    [Header("OPC UA Server")]
    public string endpointUrl =
        "opc.tcp://192.168.172.206:4840";

    [Header("Certificate")]
    public string certificatePath =
        @"C:\Users\oyste\UnityCraneClient.pfx";

    public string certificatePassword =
        "unityopcua";

    [Header("Node IDs")]
    public string slewAngleNodeId =
        "ns=1;s=Crane.SlewAngle";

    public string boomAngleNodeId =
        "ns=1;s=Crane.BoomAngle";

    public string telescopeExtensionNodeId =
        "ns=1;s=Crane.TelescopeExtension";

    [Header("Unity")]
    public CraneController craneController;

    private Session session;

    private float slewAngle;
    private float boomAngle;
    private float telescopeExtension;

    async void Start()
    {
        Debug.Log(
            "Connecting to OPC UA server: " +
            endpointUrl);

        await ConnectToServer();

        if (session != null && session.Connected)
        {
            Debug.Log("OPC UA connection successful");

            // Vi venter fortsatt med subscriptions
            // til selve session fungerer stabilt.
            //
            // CreateSubscription();
        }
        else
        {
            Debug.LogError("OPC UA connection failed");
        }
    }

    void Update()
    {
        if (craneController == null)
            return;

        craneController.slewAngle =
            slewAngle;

        craneController.boomAngle =
            boomAngle;

        craneController.telescopeExtension =
            telescopeExtension;
    }

    private async Task ConnectToServer()
    {
        try
        {
            // -------------------------------------------------
            // 1. Last OPC UA application certificate fra PFX
            // -------------------------------------------------

            if (!File.Exists(certificatePath))
            {
                Debug.LogError(
                    "PFX certificate not found:\n" +
                    certificatePath);

                return;
            }

            X509Certificate2 certificate =
                new X509Certificate2(
                    certificatePath,
                    certificatePassword,
                    X509KeyStorageFlags.Exportable |
                    X509KeyStorageFlags.PersistKeySet);

            Debug.Log(
                "Certificate loaded: " +
                certificate.Subject +
                " | HasPrivateKey: " +
                certificate.HasPrivateKey);

            if (!certificate.HasPrivateKey)
            {
                Debug.LogError(
                    "Certificate does not contain a private key.");

                return;
            }

            // -------------------------------------------------
            // 2. ApplicationConfiguration
            // -------------------------------------------------

            ApplicationConfiguration config =
                new ApplicationConfiguration
                {
                    ApplicationName =
                        "UnityCraneClient",

                    ApplicationUri =
                        "urn:UnityCraneClient",

                    ApplicationType =
                        ApplicationType.Client,

                    SecurityConfiguration =
                        new SecurityConfiguration
                        {
                            ApplicationCertificate =
                                new CertificateIdentifier
                                {
                                    Certificate =
                                        certificate
                                },

                            AutoAcceptUntrustedCertificates =
                                true
                        },

                    TransportConfigurations =
                        new TransportConfigurationCollection(),

                    TransportQuotas =
                        new TransportQuotas
                        {
                            OperationTimeout =
                                15000
                        },

                    ClientConfiguration =
                        new ClientConfiguration
                        {
                            DefaultSessionTimeout =
                                60000
                        }
                };

            await config.Validate(
                ApplicationType.Client);

            // -------------------------------------------------
            // 3. Discovery - hent ekte endpoint fra serveren
            // -------------------------------------------------

            Debug.Log(
                "Discovering OPC UA endpoints...");

            EndpointConfiguration discoveryConfiguration =
                EndpointConfiguration.Create(config);

            discoveryConfiguration.OperationTimeout =
                15000;

            EndpointDescriptionCollection endpoints;

            using (
                DiscoveryClient discoveryClient =
                    DiscoveryClient.Create(
                        new Uri(endpointUrl),
                        discoveryConfiguration))
            {
                endpoints =
                    discoveryClient.GetEndpoints(null);
            }

            Debug.Log(
                "Server returned " +
                endpoints.Count +
                " endpoint(s)");

            foreach (EndpointDescription ep in endpoints)
            {
                Debug.Log(
                    "Endpoint: " +
                    ep.EndpointUrl +
                    " | Mode: " +
                    ep.SecurityMode +
                    " | Policy: " +
                    ep.SecurityPolicyUri);
            }

            // -------------------------------------------------
            // 4. Velg None / None endpoint
            // -------------------------------------------------

            EndpointDescription selectedEndpoint =
                endpoints.FirstOrDefault(
                    ep =>
                        ep.SecurityMode ==
                            MessageSecurityMode.None
                        &&
                        ep.SecurityPolicyUri ==
                            SecurityPolicies.None);

            if (selectedEndpoint == null)
            {
                Debug.LogError(
                    "Could not find an OPC UA endpoint " +
                    "with SecurityMode=None and SecurityPolicy=None.");

                return;
            }

            Debug.Log(
                "Selected endpoint from server: " +
                selectedEndpoint.EndpointUrl);

            // -------------------------------------------------
            // 5. Sørg for at vi bruker partnerens IP
            // -------------------------------------------------

            Uri requestedUri =
                new Uri(endpointUrl);

            Uri returnedUri =
                new Uri(selectedEndpoint.EndpointUrl);

            UriBuilder correctedUri =
                new UriBuilder(returnedUri)
                {
                    Host =
                        requestedUri.Host,

                    Port =
                        requestedUri.Port
                };

            selectedEndpoint.EndpointUrl =
                correctedUri.Uri.ToString();

            Debug.Log(
                "Endpoint used for session: " +
                selectedEndpoint.EndpointUrl);

            // -------------------------------------------------
            // 6. Lag ConfiguredEndpoint
            // -------------------------------------------------

            EndpointConfiguration endpointConfiguration =
                EndpointConfiguration.Create(config);

            ConfiguredEndpoint endpoint =
                new ConfiguredEndpoint(
                    null,
                    selectedEndpoint,
                    endpointConfiguration);

            // -------------------------------------------------
            // 7. Anonymous user
            // -------------------------------------------------

            IUserIdentity userIdentity =
                new UserIdentity(
                    new AnonymousIdentityToken());

            // -------------------------------------------------
            // 8. Opprett session
            // -------------------------------------------------

            Debug.Log(
                "Creating OPC UA session...");

            session =
                await Session.Create(
                    config,
                    endpoint,
                    false,
                    "UnityCraneSession",
                    60000,
                    userIdentity,
                    null);

            Debug.Log(
                "Connected to OPC UA endpoint: " +
                session.Endpoint.EndpointUrl);
        }
        catch (Exception e)
        {
            Debug.LogError(
                "OPC UA connection error:\n" +
                e);
        }
    }

    private void OnDestroy()
    {
        try
        {
            if (session != null)
            {
                if (session.Connected)
                {
                    session.Close();
                }

                session.Dispose();
                session = null;
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning(
                "Error while closing OPC UA connection: " +
                e.Message);
        }
    }
}